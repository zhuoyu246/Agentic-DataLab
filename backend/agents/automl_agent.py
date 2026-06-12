from __future__ import annotations

from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope


class AutoMLAgent(BaseAgent):
    name = "automl_agent"
    description = "H2O AutoML first, sklearn fallback, MLflow logging integrated."

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        meta, df = ctx.active_dataframe()
        await ctx.emit("Starting AutoML flow.", agent_name=self.name)
        target = self._infer_target(df, instruction)
        if target is None:
            return AgentResult(
                message="AutoML needs a target column. Mention `target=<column>` or include a likely label column.",
                degraded=True,
            )
        engine = "sklearn_fallback"
        degraded = True
        fallback_reason: str | None = None
        try:
            if ctx.settings.get("h2o_enabled", True):
                try:
                    result = await self._run_h2o_automl(ctx, df, target)
                    engine = "h2o_automl"
                    degraded = False
                    message = "H2O AutoML completed."
                except Exception as exc:
                    fallback_reason = str(exc)
                    await ctx.emit(
                        f"H2O AutoML degraded to sklearn fallback: {exc}",
                        agent_name=self.name,
                        event_type="warning",
                    )
                    result = await self._run_sklearn_fallback(ctx, df, target)
                    message = "AutoML completed with sklearn fallback."
            else:
                result = await self._run_sklearn_fallback(ctx, df, target)
                message = "AutoML completed with sklearn fallback."
        except Exception as exc:
            return AgentResult(message=f"AutoML failed: {exc}", error=str(exc), degraded=True)
        result["engine"] = engine if engine == "h2o_automl" else result.get("engine", engine)
        if fallback_reason:
            result["fallback_reason"] = fallback_reason
        artifact = ArtifactEnvelope(
            kind="model_info",
            title="AutoML model",
            dataset_id=meta.id,
            payload=result,
            degraded=degraded,
        )
        artifacts = [artifact]
        if "charts" in result:
            for c in result.pop("charts"):
                if "kind" not in c:
                    artifacts.append(
                        ArtifactEnvelope(
                            kind="plotly_chart",
                            title=c.get("title", "Chart"),
                            dataset_id=meta.id,
                            payload={"plotly_json": c.get("plotly_json")}
                        )
                    )
                else:
                    artifacts.append(ArtifactEnvelope(**c))

        return AgentResult(
            message=message,
            artifacts=artifacts,
            metrics=result.get("metrics", {}),
            degraded=degraded,
        )

    @staticmethod
    def _infer_target(df, instruction: str) -> str | None:
        import re

        m = re.search(r"target\s*[:=]\s*([A-Za-z_][\w]*)", instruction)
        if m and m.group(1) in df.columns:
            return m.group(1)
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

    async def _run_sklearn_fallback(self, ctx: AgentContext, df, target: str) -> dict[str, Any]:
        import mlflow
        import pandas as pd
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.impute import SimpleImputer
        from sklearn.metrics import accuracy_score, r2_score
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder

        y = df[target]
        x = df.drop(columns=[target])
        categorical = [c for c in x.columns if str(x[c].dtype) in {"object", "category", "string"}]
        numeric = [c for c in x.columns if c not in categorical]
        is_classification = y.dtype == "object" or y.nunique(dropna=True) <= 20
        model = RandomForestClassifier(n_estimators=80, random_state=42) if is_classification else RandomForestRegressor(n_estimators=80, random_state=42)
        pre = ColumnTransformer(
            [
                ("num", Pipeline([("impute", SimpleImputer(strategy="median"))]), numeric),
                ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
            ]
        )
        pipe = Pipeline([("preprocess", pre), ("model", model)])
        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42)
        pipe.fit(x_train, y_train)
        preds = pipe.predict(x_test)
        metrics = (
            {"accuracy": float(accuracy_score(y_test, preds))}
            if is_classification
            else {"r2": float(r2_score(y_test, preds))}
        )
        run_id = None
        if ctx.settings.get("mlflow_enabled", True):
            try:
                mlflow.set_tracking_uri(ctx.settings.get("mlflow_tracking_uri"))
                mlflow.set_experiment(ctx.settings.get("mlflow_experiment_name", "Agentic-DataLab"))
                with mlflow.start_run(run_name=f"automl_{ctx.run_id}") as run:
                    mlflow.log_params(
                        {
                            "target": target,
                            "rows": len(df),
                            "columns": len(df.columns),
                            "engine": "sklearn_fallback",
                        }
                    )
                    mlflow.log_metrics(metrics)
                    mlflow.sklearn.log_model(pipe, artifact_path="model")
                    run_id = run.info.run_id
            except Exception as exc:
                await ctx.emit(
                    f"MLflow logging degraded: {exc}",
                    agent_name=self.name,
                    event_type="warning",
                )
        charts = []
        import json
        import numpy as np

        if is_classification:
            from sklearn.metrics import confusion_matrix, roc_curve, auc
            try:
                cm = confusion_matrix(y_test, preds)
                classes = [str(c) for c in model.classes_]
                charts.append({
                    "kind": "plotly_chart",
                    "title": "Confusion Matrix",
                    "dataset_id": ctx.active_dataset_id,
                    "payload": {
                        "plotly_json": json.dumps({
                            "data": [{
                                "z": cm.tolist(),
                                "x": classes,
                                "y": classes,
                                "type": "heatmap",
                                "colorscale": "Blues"
                            }],
                            "layout": {"title": "Confusion Matrix", "xaxis": {"title": "Predicted"}, "yaxis": {"title": "Actual"}}
                        })
                    }
                })
                
                if len(classes) == 2:
                    probs = pipe.predict_proba(x_test)[:, 1]
                    fpr, tpr, _ = roc_curve(y_test, probs, pos_label=model.classes_[1])
                    roc_auc = float(auc(fpr, tpr))
                    charts.append({
                        "kind": "plotly_chart",
                        "title": "ROC Curve",
                        "dataset_id": ctx.active_dataset_id,
                        "payload": {
                            "plotly_json": json.dumps({
                                "data": [
                                    {"x": fpr.tolist(), "y": tpr.tolist(), "type": "scatter", "mode": "lines", "name": f"ROC (AUC = {roc_auc:.2f})"},
                                    {"x": [0, 1], "y": [0, 1], "type": "scatter", "mode": "lines", "line": {"dash": "dash"}, "name": "Random"}
                                ],
                                "layout": {"title": "ROC Curve", "xaxis": {"title": "False Positive Rate"}, "yaxis": {"title": "True Positive Rate"}}
                            })
                        }
                    })
            except Exception as e:
                pass

        try:
            importances = model.feature_importances_
            feature_names = pipe.named_steps["preprocess"].get_feature_names_out()
            feature_names = [f.split("__")[-1] for f in feature_names]
            indices = np.argsort(importances)[::-1][:15]
            charts.append({
                "kind": "plotly_chart",
                "title": "Feature Importance",
                "dataset_id": ctx.active_dataset_id,
                "payload": {
                    "plotly_json": json.dumps({
                        "data": [{
                            "x": importances[indices].tolist()[::-1],
                            "y": [feature_names[i] for i in indices][::-1],
                            "type": "bar",
                            "orientation": "h"
                        }],
                        "layout": {"title": "Top Feature Importances", "margin": {"l": 150}}
                    })
                }
            })
        except Exception:
            pass

        return {
            "engine": "sklearn_fallback",
            "target": target,
            "task": "classification" if is_classification else "regression",
            "metrics": metrics,
            "run_id": run_id,
            "feature_columns": [str(c) for c in x.columns],
            "charts": charts,
        }

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
                    "The run was killed and downgraded to sklearn fallback."
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
