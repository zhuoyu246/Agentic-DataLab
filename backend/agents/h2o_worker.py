from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _configure_local_proxy_bypass() -> None:
    for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
        if key in os.environ:
            del os.environ[key]
    
    existing_no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    no_proxy_parts = [x.strip() for x in existing_no_proxy.split(",") if x.strip()]
    for item in ("localhost", "127.0.0.1", "::1"):
        if item not in no_proxy_parts:
            no_proxy_parts.append(item)
    os.environ["NO_PROXY"] = ",".join(no_proxy_parts)
    os.environ["no_proxy"] = os.environ["NO_PROXY"]


def run_h2o_automl(
    *,
    input_path: Path,
    output_path: Path,
    target: str,
    task: str,
    run_id: str,
    max_runtime_seconds: int,
    max_models: int,
    mlflow_enabled: bool,
    mlflow_tracking_uri: str | None,
    mlflow_experiment_name: str,
) -> None:
    import h2o
    import mlflow
    from h2o.automl import H2OAutoML

    _configure_local_proxy_bypass()
    h2o.no_progress()
    df = pd.read_parquet(input_path)
    h2o.init(
        ip="127.0.0.1",
        max_mem_size="2G",
        nthreads=-1,
        proxy=None,
        bind_to_localhost=True,
        verbose=False,
    )
    try:
        frame = h2o.H2OFrame(df)
        x = [c for c in frame.columns if c != target]
        y = target
        if task == "classification":
            is_classification = True
        elif task == "regression":
            is_classification = False
        else:
            is_classification = (
                str(df[target].dtype) in {"object", "category", "string", "bool"}
                or df[target].nunique(dropna=True) <= 20
            )
        if is_classification:
            frame[y] = frame[y].asfactor()
        aml = H2OAutoML(
            max_runtime_secs=max_runtime_seconds,
            max_models=max_models,
            seed=42,
            sort_metric="AUTO",
            project_name=f"agentic_datalab_{run_id[:8]}",
        )
        aml.train(x=x, y=y, training_frame=frame)
        leader = aml.leader
        if leader is None:
            raise RuntimeError(f"H2O AutoML failed to build any models within {max_runtime_seconds}s limit.")
        leaderboard = aml.leaderboard.as_data_frame()
        metrics: dict[str, float] = {}
        try:
            perf = leader.model_performance(frame)
            for name in ("auc", "rmse", "mae", "r2", "logloss"):
                fn = getattr(perf, name, None)
                if callable(fn):
                    val = fn()
                    if val is not None:
                        metrics[name] = float(val)
        except Exception:
            pass

        charts = []
        try:
            perf = leader.model_performance(frame)
            if is_classification:
                # ROC Curve
                try:
                    classes = frame[y].levels()[0] if frame[y].levels() else []
                    if len(classes) == 2:
                        fpr = getattr(perf, "fprs", [])
                        tpr = getattr(perf, "tprs", [])
                        auc_val = perf.auc()
                        if len(fpr) > 0 and len(tpr) > 0:
                            charts.append({
                                "title": "ROC Curve",
                                "plotly_json": json.dumps({
                                    "data": [
                                        {"x": list(fpr), "y": list(tpr), "type": "scatter", "mode": "lines", "name": f"ROC (AUC = {auc_val:.2f})"},
                                        {"x": [0, 1], "y": [0, 1], "type": "scatter", "mode": "lines", "line": {"dash": "dash"}, "name": "Random"}
                                    ],
                                    "layout": {"title": "ROC Curve", "xaxis": {"title": "False Positive Rate"}, "yaxis": {"title": "True Positive Rate"}}
                                })
                            })
                except Exception:
                    pass

                # Confusion Matrix
                try:
                    cm = perf.confusion_matrix()
                    if cm is not None:
                        cm_df = cm.as_data_frame()
                        classes = frame[y].levels()[0] if frame[y].levels() else []
                        if not classes:
                            classes = [str(c) for c in cm_df.columns if c not in ["Error", "Rate"]]
                        n_classes = len(classes)
                        if n_classes > 0 and n_classes <= len(cm_df):
                            matrix_data = cm_df.iloc[:n_classes, :n_classes].values.tolist()
                            charts.append({
                                "title": "Confusion Matrix",
                                "plotly_json": json.dumps({
                                    "data": [{
                                        "z": matrix_data,
                                        "x": classes,
                                        "y": classes,
                                        "type": "heatmap",
                                        "colorscale": "Blues"
                                    }],
                                    "layout": {"title": "Confusion Matrix", "xaxis": {"title": "Predicted"}, "yaxis": {"title": "Actual"}}
                                })
                            })
                except Exception:
                    pass
                # Actual / predicted class distribution
                try:
                    pred_df = leader.predict(frame).as_data_frame()
                    if "predict" in pred_df.columns:
                        actual = df[target].astype(str)
                        predicted = pred_df["predict"].astype(str)
                        actual_counts = actual.value_counts().rename_axis("class").reset_index(name="count")
                        actual_counts["series"] = "actual"
                        pred_counts = predicted.value_counts().rename_axis("class").reset_index(name="count")
                        pred_counts["series"] = "predicted"
                        dist_df = pd.concat([actual_counts, pred_counts], ignore_index=True)
                        charts.append({
                            "title": "Actual vs Predicted Class Distribution",
                            "plotly_json": json.dumps({
                                "data": [
                                    {
                                        "x": dist_df[dist_df["series"] == series]["class"].tolist(),
                                        "y": dist_df[dist_df["series"] == series]["count"].tolist(),
                                        "type": "bar",
                                        "name": series,
                                    }
                                    for series in ["actual", "predicted"]
                                ],
                                "layout": {
                                    "title": "Actual vs Predicted Class Distribution",
                                    "xaxis": {"title": "Class"},
                                    "yaxis": {"title": "Count"},
                                    "barmode": "group",
                                },
                            })
                        })
                except Exception:
                    pass
            else:
                try:
                    pred_df = leader.predict(frame).as_data_frame()
                    pred_col = "predict" if "predict" in pred_df.columns else pred_df.columns[0]
                    actual = pd.to_numeric(df[target], errors="coerce")
                    predicted = pd.to_numeric(pred_df[pred_col], errors="coerce")
                    reg_df = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
                    if not reg_df.empty:
                        reg_df["residual"] = reg_df["actual"] - reg_df["predicted"]
                        min_v = float(min(reg_df["actual"].min(), reg_df["predicted"].min()))
                        max_v = float(max(reg_df["actual"].max(), reg_df["predicted"].max()))
                        charts.append({
                            "title": "Actual vs Predicted",
                            "plotly_json": json.dumps({
                                "data": [
                                    {
                                        "x": reg_df["actual"].tolist(),
                                        "y": reg_df["predicted"].tolist(),
                                        "type": "scatter",
                                        "mode": "markers",
                                        "name": "predictions",
                                    },
                                    {
                                        "x": [min_v, max_v],
                                        "y": [min_v, max_v],
                                        "type": "scatter",
                                        "mode": "lines",
                                        "name": "perfect",
                                        "line": {"dash": "dash"},
                                    },
                                ],
                                "layout": {
                                    "title": "Actual vs Predicted",
                                    "xaxis": {"title": "Actual"},
                                    "yaxis": {"title": "Predicted"},
                                },
                            })
                        })
                        charts.append({
                            "title": "Residuals vs Predicted",
                            "plotly_json": json.dumps({
                                "data": [{
                                    "x": reg_df["predicted"].tolist(),
                                    "y": reg_df["residual"].tolist(),
                                    "type": "scatter",
                                    "mode": "markers",
                                    "name": "residuals",
                                }],
                                "layout": {
                                    "title": "Residuals vs Predicted",
                                    "xaxis": {"title": "Predicted"},
                                    "yaxis": {"title": "Residual"},
                                },
                            })
                        })
                        charts.append({
                            "title": "Residual Distribution",
                            "plotly_json": json.dumps({
                                "data": [{
                                    "x": reg_df["residual"].tolist(),
                                    "type": "histogram",
                                    "nbinsx": 40,
                                    "name": "residual",
                                }],
                                "layout": {
                                    "title": "Residual Distribution",
                                    "xaxis": {"title": "Residual"},
                                    "yaxis": {"title": "Count"},
                                },
                            })
                        })
                except Exception:
                    pass

            # Feature Importance
            try:
                varimp = leader.varimp()
                if varimp:
                    varimp = varimp[:15]
                    variables = [str(v[0]) for v in varimp]
                    importances = [float(v[1]) for v in varimp]
                    charts.append({
                        "title": "Feature Importance",
                        "plotly_json": json.dumps({
                            "data": [{
                                "x": importances[::-1],
                                "y": variables[::-1],
                                "type": "bar",
                                "orientation": "h"
                            }],
                            "layout": {"title": "Top Feature Importances", "margin": {"l": 150}}
                        })
                    })
            except Exception:
                pass
        except Exception:
            pass

        mlflow_run_id = None
        if mlflow_enabled and mlflow_tracking_uri:
            mlflow.set_tracking_uri(mlflow_tracking_uri)
            mlflow.set_experiment(mlflow_experiment_name)
            with mlflow.start_run(run_name=f"h2o_automl_{run_id}") as run:
                mlflow.log_params(
                    {
                        "target": target,
                        "rows": len(df),
                        "columns": len(df.columns),
                        "engine": "h2o_automl",
                        "leader_model_id": leader.model_id,
                        "max_models": max_models,
                        "max_runtime_seconds": max_runtime_seconds,
                    }
                )
                if metrics:
                    mlflow.log_metrics(metrics)
                top = leaderboard.head(20).where(pd.notnull(leaderboard.head(20)), None)
                mlflow.log_dict(top.to_dict(orient="records"), "leaderboard_top20.json")
                mlflow_run_id = run.info.run_id

        top = leaderboard.head(20).where(pd.notnull(leaderboard.head(20)), None)
        result = {
            "engine": "h2o_automl",
            "target": target,
            "leader_model_id": leader.model_id,
            "task": "classification" if is_classification else "regression",
            "metrics": metrics,
            "leaderboard": top.to_dict(orient="records"),
            "run_id": mlflow_run_id,
            "feature_columns": [str(c) for c in x],
            "charts": charts,
        }
        output_path.write_text(
            json.dumps(_json_safe(result), ensure_ascii=False),
            encoding="utf-8",
        )
    finally:
        try:
            h2o.cluster().shutdown(prompt=False)
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--task", choices=["auto", "classification", "regression"], default="auto")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-runtime-seconds", type=int, required=True)
    parser.add_argument("--max-models", type=int, required=True)
    parser.add_argument("--mlflow-enabled", action="store_true")
    parser.add_argument("--mlflow-tracking-uri", default=None)
    parser.add_argument("--mlflow-experiment-name", default="Agentic-DataLab")
    args = parser.parse_args()
    run_h2o_automl(
        input_path=Path(args.input),
        output_path=Path(args.output),
        target=args.target,
        task=args.task,
        run_id=args.run_id,
        max_runtime_seconds=args.max_runtime_seconds,
        max_models=args.max_models,
        mlflow_enabled=args.mlflow_enabled,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        mlflow_experiment_name=args.mlflow_experiment_name,
    )


if __name__ == "__main__":
    main()
