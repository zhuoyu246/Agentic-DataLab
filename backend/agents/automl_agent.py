"""
AutoMLAgent - supervised and lightweight unsupervised ML workflows.

The H2O path is still used when available for supervised tabular training.
The sklearn fallback is now a real adaptive pipeline: classification,
regression, clustering, and anomaly detection with type-aware preprocessing,
MLflow logging, HITL gating, and a richer diagnostics chart suite.
"""
from __future__ import annotations

import hashlib
from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import AgentEvent, AgentRunStatus, ApprovalRequest, ArtifactEnvelope


def _flatten_text_values(values):
    if hasattr(values, "to_numpy"):
        values = values.to_numpy()
    return values.astype(str).ravel()


AUTOML_PROMPT = """\
You are an AutoML training specialist. Support these workflows:

1. Supervised classification/regression with target inference.
2. Clustering/segmentation when the prompt asks for clusters without a target.
3. Anomaly/outlier detection when the prompt asks for abnormal records.
4. Adaptive preprocessing: numeric impute/scale, low-cardinality one-hot,
   medium/high-cardinality ordinal/frequency signals, free text Tf-Idf,
   datetime expansion, and safe ID handling.
5. Diagnostics: metrics, feature importance, confusion matrix, ROC/PR,
   residual charts, cluster maps, anomaly score charts, and MLflow logging.
"""


class AutoMLAgent(BaseAgent):
    name = "automl_agent"
    description = "Adaptive AutoML for classification, regression, clustering, and anomaly detection."

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        meta, df = ctx.active_dataframe()
        await ctx.emit("Starting adaptive AutoML flow.", agent_name=self.name)

        target = self._infer_target(df, instruction)
        task = self._infer_task(df, instruction, target)
        if task in {"classification", "regression"} and target is None:
            return AgentResult(
                message=(
                    "Supervised AutoML needs a target column. Mention `target=<column>` "
                    "or ask for clustering/anomaly detection."
                ),
                degraded=True,
            )

        approval_key = self._approval_key(
            meta.fingerprint or meta.schema_hash or meta.id,
            target or task,
            instruction,
        )
        train_payload = {
            "approval_key": approval_key,
            "dataset_id": meta.id,
            "dataset_label": meta.label,
            "rows": int(df.shape[0]),
            "columns": int(df.shape[1]),
            "target": target,
            "task": task,
            "engine": "h2o_automl" if task in {"classification", "regression"} and ctx.settings.get("h2o_enabled", True) else "sklearn_adaptive",
            "h2o_enabled": bool(ctx.settings.get("h2o_enabled", True)),
            "mlflow_enabled": bool(ctx.settings.get("mlflow_enabled", True)),
        }
        if (
            ctx.settings.get("require_human_approval", True)
            and ctx.requires_approval("automl.train", train_payload)
            and not ctx.approvals.get(approval_key, False)
        ):
            approval = ApprovalRequest(
                session_id=ctx.session_id,
                run_id=ctx.run_id,
                tool_name="automl.train",
                reason="AutoML can consume significant CPU, memory, and MLflow storage.",
                proposed_action=train_payload,
            )
            await ctx.events.publish(
                AgentEvent(
                    session_id=ctx.session_id,
                    run_id=ctx.run_id,
                    type="approval_required",
                    status=AgentRunStatus.WAITING_APPROVAL,
                    agent_name=self.name,
                    message=approval.reason,
                    payload=approval.model_dump(mode="json"),
                )
            )
            return AgentResult(
                message=f"AutoML is waiting for approval to run `{task}`.",
                artifacts=[
                    ArtifactEnvelope(
                        kind="approval_required",
                        title="AutoML approval required",
                        dataset_id=meta.id,
                        payload=approval.model_dump(mode="json"),
                    )
                ],
                metrics={"waiting_approval": True, "approval_id": approval.id},
                status=AgentRunStatus.WAITING_APPROVAL,
            )

        engine = "sklearn_adaptive"
        degraded = task in {"classification", "regression"}
        fallback_reason: str | None = None
        try:
            if task in {"classification", "regression"} and ctx.settings.get("h2o_enabled", True):
                try:
                    max_runtime = int(ctx.settings.get("h2o_max_runtime_seconds", 300))
                    outer_timeout = int(
                        ctx.settings.get(
                            "h2o_outer_timeout_seconds",
                            max(90, max_runtime + 45),
                        )
                    )
                    max_models = int(ctx.settings.get("h2o_max_models", 8))
                    await ctx.emit(
                        (
                            "H2O AutoML worker launched "
                            f"(max_runtime={max_runtime}s, "
                            f"outer_timeout={outer_timeout}s, "
                            f"max_models={max_models})."
                        ),
                        agent_name=self.name,
                    )
                    result = await self._run_h2o_automl(ctx, df, target or "")
                    engine = "h2o_automl"
                    degraded = False
                    message = "H2O AutoML completed."
                except Exception as exc:
                    fallback_reason = str(exc)
                    await ctx.emit(
                        f"H2O AutoML degraded to sklearn adaptive pipeline: {exc}",
                        agent_name=self.name,
                        event_type="warning",
                    )
                    result = await self._run_sklearn_adaptive(ctx, df, target, task)
                    message = f"AutoML completed with sklearn adaptive {task} pipeline."
            else:
                result = await self._run_sklearn_adaptive(ctx, df, target, task)
                message = f"AutoML completed with sklearn adaptive {task} pipeline."
                degraded = False if task in {"clustering", "anomaly_detection"} else degraded
        except Exception as exc:
            return AgentResult(message=f"AutoML failed: {exc}", error=str(exc), degraded=True)

        result["engine"] = engine if engine == "h2o_automl" else result.get("engine", engine)
        if fallback_reason:
            result["fallback_reason"] = fallback_reason

        charts = result.pop("charts", [])
        artifact = ArtifactEnvelope(
            kind="model_info",
            title="AutoML model",
            dataset_id=meta.id,
            payload=result,
            degraded=degraded,
        )
        artifacts = [artifact]
        for chart in charts:
            artifacts.append(ArtifactEnvelope(**chart))

        return AgentResult(
            message=message,
            artifacts=artifacts,
            metrics=result.get("metrics", {}),
            degraded=degraded,
        )

    @staticmethod
    def _infer_target(df, instruction: str) -> str | None:
        import re

        m = re.search(r"target\s*[:=]\s*([A-Za-z_][\w]*)", instruction or "")
        if m and m.group(1) in df.columns:
            return m.group(1)
        lowered = (instruction or "").lower()
        for col in df.columns:
            col_lower = str(col).lower()
            if f"predict {col_lower}" in lowered or f"预测{col_lower}" in lowered:
                return str(col)
        for candidate in (
            "target",
            "label",
            "y",
            "churn",
            "class",
            "diagnosis",
            "cancer",
            "outcome",
            "result",
            "risk",
            "disease",
        ):
            for col in df.columns:
                col_lower = str(col).lower()
                if col_lower == candidate or candidate in col_lower:
                    return str(col)
        return str(df.columns[-1]) if len(df.columns) >= 2 else None

    @staticmethod
    def _infer_task(df, instruction: str, target: str | None) -> str:
        text = (instruction or "").lower()
        if any(w in text for w in ["anomaly", "outlier", "fraud", "异常", "离群"]):
            return "anomaly_detection"
        if any(w in text for w in ["cluster", "clustering", "segment", "segmentation", "聚类", "分群"]):
            return "clustering"
        if target is None:
            return "classification"
        y = df[target]
        if str(y.dtype) in {"object", "category", "string", "bool", "boolean"}:
            return "classification"
        unique = int(y.nunique(dropna=True))
        return "classification" if unique <= min(30, max(12, len(y) // 20)) else "regression"

    @staticmethod
    def _approval_key(dataset_id: str, target_or_task: str, instruction: str) -> str:
        payload = f"{dataset_id}:{target_or_task}:{instruction}"
        digest = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()
        return f"automl:{digest}"

    async def _run_sklearn_adaptive(
        self,
        ctx: AgentContext,
        df,
        target: str | None,
        task: str,
    ) -> dict[str, Any]:
        import asyncio

        result = await asyncio.to_thread(
            self._run_sklearn_adaptive_sync,
            ctx,
            df,
            target,
            task,
        )
        mlflow_warning = result.pop("_mlflow_warning", None)
        if mlflow_warning:
            await ctx.emit(mlflow_warning, agent_name=self.name, event_type="warning")
        return result

    def _run_sklearn_adaptive_sync(
        self,
        ctx: AgentContext,
        df,
        target: str | None,
        task: str,
    ) -> dict[str, Any]:
        if task == "clustering":
            return self._run_clustering_sync(ctx, df)
        if task == "anomaly_detection":
            return self._run_anomaly_sync(ctx, df)
        return self._run_supervised_sync(ctx, df, target or "", task)

    def _run_supervised_sync(self, ctx: AgentContext, df, target: str, task: str) -> dict[str, Any]:
        import mlflow
        import numpy as np
        from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor, RandomForestClassifier, RandomForestRegressor
        from sklearn.metrics import (
            accuracy_score,
            balanced_accuracy_score,
            f1_score,
            mean_absolute_error,
            mean_squared_error,
            precision_score,
            r2_score,
            recall_score,
            roc_auc_score,
        )
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline

        frame = df.dropna(subset=[target]).copy()
        y = frame[target]
        x = frame.drop(columns=[target])
        x, prep_notes = self._prepare_model_frame(x)
        preprocessor, prep_profile = self._build_preprocessor(x)

        stratify = None
        if task == "classification":
            counts = y.value_counts(dropna=False)
            if len(counts) > 1 and int(counts.min()) >= 2:
                stratify = y
        x_train, x_test, y_train, y_test = train_test_split(
            x,
            y,
            test_size=0.2,
            random_state=42,
            stratify=stratify,
        )
        if task == "classification":
            candidates = {
                "random_forest": RandomForestClassifier(n_estimators=140, random_state=42, n_jobs=-1),
                "extra_trees": ExtraTreesClassifier(n_estimators=180, random_state=42, n_jobs=-1),
            }
            scorer = lambda yt, yp: f1_score(yt, yp, average="macro", zero_division=0)
        else:
            candidates = {
                "random_forest": RandomForestRegressor(n_estimators=140, random_state=42, n_jobs=-1),
                "extra_trees": ExtraTreesRegressor(n_estimators=180, random_state=42, n_jobs=-1),
            }
            scorer = lambda yt, yp: -mean_absolute_error(yt, yp)

        best_name = ""
        best_score = float("-inf")
        best_pipe = None
        best_preds = None
        for name, model in candidates.items():
            pipe = Pipeline([("preprocess", preprocessor), ("model", model)])
            pipe.fit(x_train, y_train)
            preds = pipe.predict(x_test)
            score = float(scorer(y_test, preds))
            if score > best_score:
                best_name = name
                best_score = score
                best_pipe = pipe
                best_preds = preds
        if best_pipe is None or best_preds is None:
            raise RuntimeError("No sklearn candidate model completed.")

        metrics: dict[str, float] = {}
        proba = None
        if task == "classification":
            metrics = {
                "accuracy": float(accuracy_score(y_test, best_preds)),
                "balanced_accuracy": float(balanced_accuracy_score(y_test, best_preds)),
                "f1_macro": float(f1_score(y_test, best_preds, average="macro", zero_division=0)),
                "precision_macro": float(precision_score(y_test, best_preds, average="macro", zero_division=0)),
                "recall_macro": float(recall_score(y_test, best_preds, average="macro", zero_division=0)),
            }
            if hasattr(best_pipe, "predict_proba"):
                try:
                    proba = best_pipe.predict_proba(x_test)
                    if proba is not None and proba.shape[1] > 1:
                        metrics["roc_auc_ovr"] = float(roc_auc_score(y_test, proba, multi_class="ovr"))
                except Exception:
                    proba = None
        else:
            rmse = float(mean_squared_error(y_test, best_preds) ** 0.5)
            metrics = {
                "r2": float(r2_score(y_test, best_preds)),
                "mae": float(mean_absolute_error(y_test, best_preds)),
                "rmse": rmse,
            }

        run_id, mlflow_warning = self._log_mlflow(
            ctx,
            best_pipe,
            task=task,
            metrics=metrics,
            params={
                "target": target,
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "engine": "sklearn_adaptive",
                "best_model": best_name,
            },
        )
        feature_names = self._feature_names(best_pipe)
        charts = (
            self._classification_charts(ctx, y_test, best_preds, proba, best_pipe, feature_names)
            if task == "classification"
            else self._regression_charts(ctx, y_test, best_preds, best_pipe, feature_names)
        )
        result = {
            "engine": "sklearn_adaptive",
            "task": task,
            "target": target,
            "best_model": best_name,
            "metrics": metrics,
            "run_id": run_id,
            "feature_columns": [str(c) for c in x.columns],
            "preprocessing": {**prep_profile, **prep_notes},
            "charts": charts,
        }
        if mlflow_warning:
            result["_mlflow_warning"] = mlflow_warning
        return result

    def _run_clustering_sync(self, ctx: AgentContext, df) -> dict[str, Any]:
        import mlflow
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        from sklearn.pipeline import Pipeline

        x, prep_notes = self._prepare_model_frame(df.copy())
        preprocessor, prep_profile = self._build_preprocessor(x)
        n_clusters = max(2, min(8, int(len(x) ** 0.5))) if len(x) >= 4 else 2
        pipe = Pipeline([
            ("preprocess", preprocessor),
            ("model", KMeans(n_clusters=n_clusters, random_state=42, n_init=10)),
        ])
        labels = pipe.fit_predict(x)
        transformed = pipe.named_steps["preprocess"].transform(x)
        metrics = {"clusters": float(n_clusters), "inertia": float(pipe.named_steps["model"].inertia_)}
        try:
            metrics["silhouette"] = float(silhouette_score(transformed, labels))
        except Exception:
            pass
        run_id, mlflow_warning = self._log_mlflow(
            ctx,
            pipe,
            task="clustering",
            metrics=metrics,
            params={"rows": int(len(df)), "columns": int(len(df.columns)), "engine": "sklearn_adaptive"},
        )
        charts = self._cluster_charts(ctx, transformed, labels, x)
        result = {
            "engine": "sklearn_adaptive",
            "task": "clustering",
            "target": None,
            "best_model": "kmeans",
            "metrics": metrics,
            "run_id": run_id,
            "feature_columns": [str(c) for c in x.columns],
            "preprocessing": {**prep_profile, **prep_notes},
            "cluster_counts": {str(k): int(v) for k, v in self._value_counts(labels).items()},
            "charts": charts,
        }
        if mlflow_warning:
            result["_mlflow_warning"] = mlflow_warning
        return result

    def _run_anomaly_sync(self, ctx: AgentContext, df) -> dict[str, Any]:
        from sklearn.ensemble import IsolationForest
        from sklearn.pipeline import Pipeline

        x, prep_notes = self._prepare_model_frame(df.copy())
        preprocessor, prep_profile = self._build_preprocessor(x)
        contamination = min(0.1, max(0.01, 20 / max(len(x), 1)))
        pipe = Pipeline([
            ("preprocess", preprocessor),
            ("model", IsolationForest(contamination=contamination, random_state=42, n_jobs=-1)),
        ])
        raw_labels = pipe.fit_predict(x)
        labels = (raw_labels == -1).astype(int)
        scores = -pipe.named_steps["model"].score_samples(pipe.named_steps["preprocess"].transform(x))
        metrics = {
            "anomaly_count": float(labels.sum()),
            "anomaly_rate": float(labels.mean()),
            "contamination": float(contamination),
        }
        run_id, mlflow_warning = self._log_mlflow(
            ctx,
            pipe,
            task="anomaly_detection",
            metrics=metrics,
            params={"rows": int(len(df)), "columns": int(len(df.columns)), "engine": "sklearn_adaptive"},
        )
        transformed = pipe.named_steps["preprocess"].transform(x)
        charts = self._anomaly_charts(ctx, transformed, labels, scores)
        result = {
            "engine": "sklearn_adaptive",
            "task": "anomaly_detection",
            "target": None,
            "best_model": "isolation_forest",
            "metrics": metrics,
            "run_id": run_id,
            "feature_columns": [str(c) for c in x.columns],
            "preprocessing": {**prep_profile, **prep_notes},
            "charts": charts,
        }
        if mlflow_warning:
            result["_mlflow_warning"] = mlflow_warning
        return result

    def _prepare_model_frame(self, x):
        import pandas as pd

        x = x.copy()
        expanded_datetime: list[str] = []
        dropped_id_like: list[str] = []
        for col in list(x.columns):
            name = str(col)
            if self._looks_like_id(name):
                dropped_id_like.append(name)
                x = x.drop(columns=[col])
                continue
            if pd.api.types.is_datetime64_any_dtype(x[col]) or any(t in name.lower() for t in ("date", "time", "timestamp")):
                converted = pd.to_datetime(x[col], errors="coerce")
                if converted.notna().mean() >= 0.7:
                    x[f"{name}__year"] = converted.dt.year
                    x[f"{name}__month"] = converted.dt.month
                    x[f"{name}__day"] = converted.dt.day
                    x[f"{name}__weekday"] = converted.dt.weekday
                    x = x.drop(columns=[col])
                    expanded_datetime.append(name)
        for col in x.select_dtypes(include=["bool", "boolean"]).columns:
            x[col] = x[col].astype("Int8")
        for col in x.select_dtypes(include=["object", "string", "category"]).columns:
            avg_len = float(x[col].astype("string").dropna().str.len().mean() or 0)
            if avg_len >= 30:
                x[col] = x[col].astype("string").fillna("").astype(str)
        return x, {"expanded_datetime": expanded_datetime, "dropped_id_like": dropped_id_like}

    def _build_preprocessor(self, x):
        from sklearn.compose import ColumnTransformer
        from sklearn.impute import SimpleImputer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OrdinalEncoder, StandardScaler, FunctionTransformer
        from sklearn.feature_extraction.text import TfidfVectorizer

        numeric_cols = [str(c) for c in x.select_dtypes(include=["number", "bool", "boolean"]).columns]
        cat_cols = [str(c) for c in x.select_dtypes(include=["object", "string", "category"]).columns]
        text_cols: list[str] = []
        low_card_cols: list[str] = []
        ordinal_cols: list[str] = []
        for col in cat_cols:
            nunique = int(x[col].nunique(dropna=True))
            avg_len = float(x[col].astype("string").dropna().str.len().mean() or 0)
            if avg_len >= 30:
                text_cols.append(col)
            elif nunique <= 20:
                low_card_cols.append(col)
            else:
                ordinal_cols.append(col)

        transformers = []
        if numeric_cols:
            transformers.append(
                (
                    "num",
                    Pipeline([
                        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                        ("scale", StandardScaler(with_mean=False)),
                    ]),
                    numeric_cols,
                )
            )
        if low_card_cols:
            transformers.append(
                (
                    "onehot",
                    Pipeline([
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", self._one_hot_encoder()),
                    ]),
                    low_card_cols,
                )
            )
        if ordinal_cols:
            transformers.append(
                (
                    "ordinal",
                    Pipeline([
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("ordinal", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
                    ]),
                    ordinal_cols,
                )
            )
        for col in text_cols:
            transformers.append(
                (
                    f"tfidf_{col}",
                    Pipeline([
                        ("flatten", FunctionTransformer(_flatten_text_values, validate=False)),
                        ("tfidf", TfidfVectorizer(max_features=80, ngram_range=(1, 2))),
                    ]),
                    [col],
                )
            )
        if not transformers:
            transformers.append(("empty", "drop", []))
        preprocessor = ColumnTransformer(transformers, sparse_threshold=0.3, remainder="drop")
        profile = {
            "numeric_columns": numeric_cols,
            "one_hot_columns": low_card_cols,
            "ordinal_columns": ordinal_cols,
            "text_tfidf_columns": text_cols,
        }
        return preprocessor, profile

    @staticmethod
    def _one_hot_encoder():
        from sklearn.preprocessing import OneHotEncoder

        try:
            return OneHotEncoder(handle_unknown="ignore", sparse_output=True)
        except TypeError:
            return OneHotEncoder(handle_unknown="ignore", sparse=True)

    def _log_mlflow(self, ctx: AgentContext, model, *, task: str, metrics: dict[str, float], params: dict[str, Any]):
        run_id = None
        warning = None
        if not ctx.settings.get("mlflow_enabled", True):
            return run_id, warning
        try:
            import mlflow

            mlflow.set_tracking_uri(ctx.settings.get("mlflow_tracking_uri"))
            mlflow.set_experiment(ctx.settings.get("mlflow_experiment_name", "Agentic-DataLab"))
            with mlflow.start_run(run_name=f"automl_{task}_{ctx.run_id}") as run:
                mlflow.log_params(params)
                mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
                mlflow.sklearn.log_model(model, artifact_path="model")
                run_id = run.info.run_id
        except Exception as exc:
            warning = f"MLflow logging degraded: {exc}"
        return run_id, warning

    def _classification_charts(self, ctx: AgentContext, y_true, y_pred, proba, pipe, feature_names: list[str]):
        import numpy as np
        import pandas as pd
        import plotly.express as px
        import plotly.graph_objects as go
        from sklearn.metrics import confusion_matrix, precision_recall_curve, roc_curve, auc, classification_report

        charts = []
        classes = [str(c) for c in getattr(pipe.named_steps["model"], "classes_", sorted(pd.Series(y_true).dropna().unique()))]
        cm = confusion_matrix(y_true, y_pred)
        charts.append(self._chart(ctx, "Confusion Matrix", go.Figure(data=go.Heatmap(z=cm.tolist(), x=classes, y=classes, colorscale="Blues"))))

        report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
        rows = []
        for label, values in report.items():
            if isinstance(values, dict) and label not in {"accuracy", "macro avg", "weighted avg"}:
                rows.append({"class": str(label), "precision": values["precision"], "recall": values["recall"], "f1": values["f1-score"]})
        if rows:
            metric_df = pd.DataFrame(rows).melt(id_vars="class", var_name="metric", value_name="score")
            charts.append(self._chart(ctx, "Per-Class Metrics", px.bar(metric_df, x="class", y="score", color="metric", barmode="group")))

        dist = pd.DataFrame({"actual": pd.Series(y_true).astype(str), "predicted": pd.Series(y_pred).astype(str)})
        dist_df = pd.concat([
            dist["actual"].value_counts().rename_axis("class").reset_index(name="count").assign(series="actual"),
            dist["predicted"].value_counts().rename_axis("class").reset_index(name="count").assign(series="predicted"),
        ])
        charts.append(self._chart(ctx, "Actual vs Predicted Class Distribution", px.bar(dist_df, x="class", y="count", color="series", barmode="group")))

        if proba is not None and proba.shape[1] == 2:
            positive = pipe.named_steps["model"].classes_[1]
            y_binary = (pd.Series(y_true).values == positive).astype(int)
            fpr, tpr, _ = roc_curve(y_binary, proba[:, 1])
            roc_auc = float(auc(fpr, tpr))
            roc_fig = go.Figure()
            roc_fig.add_trace(go.Scatter(x=fpr, y=tpr, mode="lines", name=f"ROC AUC={roc_auc:.3f}"))
            roc_fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line={"dash": "dash"}, name="Random"))
            charts.append(self._chart(ctx, "ROC Curve", roc_fig))

            precision, recall, _ = precision_recall_curve(y_binary, proba[:, 1])
            pr_fig = go.Figure(data=go.Scatter(x=recall, y=precision, mode="lines", name="PR"))
            charts.append(self._chart(ctx, "Precision-Recall Curve", pr_fig))

        if proba is not None:
            confidence = pd.DataFrame({"confidence": np.max(proba, axis=1)})
            charts.append(self._chart(ctx, "Prediction Confidence", px.histogram(confidence, x="confidence", nbins=30)))

        charts.extend(self._feature_importance_charts(ctx, pipe, feature_names))
        return charts

    def _regression_charts(self, ctx: AgentContext, y_true, y_pred, pipe, feature_names: list[str]):
        import pandas as pd
        import plotly.express as px
        import plotly.graph_objects as go

        data = pd.DataFrame({"actual": y_true, "predicted": y_pred})
        data["residual"] = data["actual"] - data["predicted"]
        charts = [
            self._chart(ctx, "Actual vs Predicted", px.scatter(data, x="actual", y="predicted")),
            self._chart(ctx, "Residuals vs Predicted", px.scatter(data, x="predicted", y="residual")),
            self._chart(ctx, "Residual Distribution", px.histogram(data, x="residual", nbins=40)),
        ]
        min_v = float(min(data["actual"].min(), data["predicted"].min()))
        max_v = float(max(data["actual"].max(), data["predicted"].max()))
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data["actual"], y=data["predicted"], mode="markers", name="predictions"))
        fig.add_trace(go.Scatter(x=[min_v, max_v], y=[min_v, max_v], mode="lines", name="perfect", line={"dash": "dash"}))
        charts[0] = self._chart(ctx, "Actual vs Predicted", fig)
        charts.extend(self._feature_importance_charts(ctx, pipe, feature_names))
        return charts

    def _cluster_charts(self, ctx: AgentContext, transformed, labels, x):
        import pandas as pd
        import plotly.express as px

        coords = self._project_2d(transformed)
        df_plot = pd.DataFrame({"x": coords[:, 0], "y": coords[:, 1], "cluster": [str(v) for v in labels]})
        counts = df_plot["cluster"].value_counts().rename_axis("cluster").reset_index(name="count")
        charts = [
            self._chart(ctx, "Cluster Map", px.scatter(df_plot, x="x", y="y", color="cluster")),
            self._chart(ctx, "Cluster Sizes", px.bar(counts, x="cluster", y="count")),
        ]
        numeric = x.select_dtypes(include=["number"]).copy()
        if not numeric.empty:
            numeric["cluster"] = labels
            profile = numeric.groupby("cluster").mean(numeric_only=True).iloc[:, :20]
            charts.append(self._chart(ctx, "Cluster Numeric Profile", px.imshow(profile, aspect="auto", color_continuous_scale="RdBu_r")))
        return charts

    def _anomaly_charts(self, ctx: AgentContext, transformed, labels, scores):
        import pandas as pd
        import plotly.express as px

        coords = self._project_2d(transformed)
        df_plot = pd.DataFrame({"x": coords[:, 0], "y": coords[:, 1], "anomaly": ["anomaly" if v else "normal" for v in labels], "score": scores})
        counts = df_plot["anomaly"].value_counts().rename_axis("label").reset_index(name="count")
        return [
            self._chart(ctx, "Anomaly Map", px.scatter(df_plot, x="x", y="y", color="anomaly", hover_data=["score"])),
            self._chart(ctx, "Anomaly Score Distribution", px.histogram(df_plot, x="score", color="anomaly", nbins=40)),
            self._chart(ctx, "Anomaly Counts", px.bar(counts, x="label", y="count")),
        ]

    def _feature_importance_charts(self, ctx: AgentContext, pipe, feature_names: list[str]):
        import numpy as np
        import pandas as pd
        import plotly.express as px

        model = pipe.named_steps["model"]
        values = getattr(model, "feature_importances_", None)
        if values is None:
            return []
        if len(feature_names) != len(values):
            feature_names = [f"feature_{i}" for i in range(len(values))]
        indices = np.argsort(values)[::-1][:20]
        data = pd.DataFrame({
            "feature": [feature_names[i] for i in indices][::-1],
            "importance": [float(values[i]) for i in indices][::-1],
        })
        return [self._chart(ctx, "Feature Importance", px.bar(data, x="importance", y="feature", orientation="h"))]

    def _chart(self, ctx: AgentContext, title: str, fig):
        import plotly.io as pio

        fig.update_layout(template="plotly_white", title=title, margin=dict(l=42, r=24, t=48, b=38))
        return {
            "kind": "plotly_chart",
            "title": title,
            "dataset_id": ctx.active_dataset_id,
            "payload": {"plotly_json": pio.to_json(fig, validate=False, remove_uids=True)},
        }

    @staticmethod
    def _feature_names(pipe) -> list[str]:
        try:
            return [str(name).split("__")[-1] for name in pipe.named_steps["preprocess"].get_feature_names_out()]
        except Exception:
            return []

    @staticmethod
    def _project_2d(values):
        import numpy as np
        from scipy import sparse
        from sklearn.decomposition import PCA, TruncatedSVD

        if values.shape[0] < 2:
            return np.zeros((values.shape[0], 2))
        if values.shape[1] < 2:
            dense = values.toarray() if sparse.issparse(values) else values
            return np.column_stack([dense[:, 0], np.zeros(values.shape[0])])
        if sparse.issparse(values):
            reducer = TruncatedSVD(n_components=2, random_state=42)
            return reducer.fit_transform(values)
        reducer = PCA(n_components=2, random_state=42)
        return reducer.fit_transform(values)

    @staticmethod
    def _value_counts(values):
        import pandas as pd

        return pd.Series(values).value_counts().sort_index()

    @staticmethod
    def _looks_like_id(name: str) -> bool:
        lowered = name.lower()
        return lowered in {"id", "uuid", "guid"} or lowered.endswith("_id") or lowered.endswith("id")

    async def _run_h2o_automl(self, ctx: AgentContext, df, target: str) -> dict[str, Any]:
        import asyncio

        return await asyncio.to_thread(self._run_h2o_worker_process, ctx, df, target)

    def _run_h2o_worker_process(self, ctx: AgentContext, df, target: str) -> dict[str, Any]:
        import json
        import os
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        max_runtime = int(ctx.settings.get("h2o_max_runtime_seconds", 300))
        outer_timeout = int(ctx.settings.get("h2o_outer_timeout_seconds", max(90, max_runtime + 45)))
        max_models = int(ctx.settings.get("h2o_max_models", 8))
        worker = Path(__file__).with_name("h2o_worker.py")
        backend_dir = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory(prefix="agentic_h2o_") as tmp:
            tmp_dir = Path(tmp)
            input_path = tmp_dir / "input.pkl"
            output_path = tmp_dir / "output.json"
            df.to_pickle(input_path)
            args = [
                sys.executable,
                str(worker),
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--target",
                target,
                "--run-id",
                ctx.run_id,
                "--max-runtime-seconds",
                str(max_runtime),
                "--max-models",
                str(max_models),
                "--mlflow-experiment-name",
                str(ctx.settings.get("mlflow_experiment_name", "Agentic-DataLab")),
            ]
            if ctx.settings.get("mlflow_enabled", True):
                args.append("--mlflow-enabled")
                tracking_uri = ctx.settings.get("mlflow_tracking_uri")
                if tracking_uri:
                    args.extend(["--mlflow-tracking-uri", str(tracking_uri)])

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            proc = subprocess.Popen(
                args,
                cwd=str(backend_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            try:
                stdout, stderr = proc.communicate(timeout=outer_timeout)
            except subprocess.TimeoutExpired as exc:
                self._kill_process_tree(proc.pid)
                raise TimeoutError(
                    f"H2O worker exceeded outer timeout {outer_timeout}s. "
                    "The run was killed and downgraded to sklearn adaptive pipeline."
                ) from exc
            if proc.returncode != 0:
                detail = self._tail(stderr or stdout or "unknown H2O worker error")
                raise RuntimeError(f"H2O worker failed: {detail}")
            if not output_path.exists():
                detail = self._tail(stderr or stdout or "missing output.json")
                raise RuntimeError(f"H2O worker did not produce output: {detail}")
            result = json.loads(output_path.read_text(encoding="utf-8"))
            if stderr:
                result["worker_stderr_tail"] = self._tail(stderr)
            return result

    @staticmethod
    def _kill_process_tree(pid: int) -> None:
        import os
        import signal
        import subprocess

        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                os.killpg(pid, signal.SIGKILL)
            except Exception:
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass

    @staticmethod
    def _tail(text: str, limit: int = 2000) -> str:
        cleaned = text.strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[-limit:]
