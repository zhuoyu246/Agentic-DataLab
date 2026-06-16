"""
FeatureEngineeringAgent - type-aware, model-agnostic feature derivation.

This agent deliberately avoids baking a single encoding strategy into the
dataset. It creates robust derived features and records preprocessing advice;
the AutoML pipeline then chooses one-hot, ordinal, hashing/Tf-Idf, scaling, or
passthrough per column at training time.
"""
from __future__ import annotations

import re

import pandas as pd

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope

FEATURE_PROMPT = """\
You are an expert ML feature engineer. Produce model-ready signals without
destroying target integrity:

1. Preserve target columns exactly.
2. Expand datetime columns into calendar and cyclic features.
3. Cast booleans to numeric flags.
4. Add missingness indicators for columns with meaningful missing rates.
5. Add frequency encodings for non-ID high-cardinality categoricals.
6. Leave raw categorical/text columns available for the model pipeline, which
   can decide one-hot, ordinal, Tf-Idf, hashing, scaling, or passthrough.
"""


class FeatureEngineeringAgent(BaseAgent):
    name = "feature_engineering_agent"
    description = "Model-agnostic feature derivation and preprocessing metadata."

    missing_indicator_threshold = 0.05
    high_cardinality_threshold = 30
    text_avg_length_threshold = 30

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        meta, df = ctx.active_dataframe()
        await ctx.emit("Creating model-ready feature signals.", agent_name=self.name)

        out = df.copy()
        target = self._infer_target(out, instruction)
        target_set = {target} if target else set()

        missing_indicators: list[str] = []
        for col in list(out.columns):
            if str(col) in target_set:
                continue
            missing_rate = float(out[col].isna().mean())
            if missing_rate >= self.missing_indicator_threshold:
                flag = f"{col}__was_missing"
                out[flag] = out[col].isna().astype("int8")
                missing_indicators.append(str(col))

        datetime_features: list[str] = []
        for col in list(out.columns):
            if str(col) in target_set or str(col).endswith("__was_missing"):
                continue
            converted = self._try_datetime(out[col], str(col))
            if converted is None:
                continue
            out[f"{col}__year"] = converted.dt.year
            out[f"{col}__month"] = converted.dt.month
            out[f"{col}__day"] = converted.dt.day
            out[f"{col}__weekday"] = converted.dt.weekday
            out[f"{col}__is_month_end"] = converted.dt.is_month_end.astype("int8")
            out[f"{col}__month_sin"] = self._cyclic_sin(converted.dt.month.fillna(0), 12)
            out[f"{col}__month_cos"] = self._cyclic_cos(converted.dt.month.fillna(0), 12)
            out = out.drop(columns=[col])
            datetime_features.append(str(col))

        bool_features: list[str] = []
        for col in out.select_dtypes(include=["bool", "boolean"]).columns:
            if str(col) in target_set:
                continue
            out[col] = out[col].astype("Int8")
            bool_features.append(str(col))

        categorical_profile = self._categorical_profile(out, target)
        frequency_encoded: list[str] = []
        for col, profile in categorical_profile.items():
            if profile["strategy"] != "frequency_encode":
                continue
            freq_col = f"{col}__frequency"
            freq = out[col].astype("string").fillna("<missing>").value_counts(normalize=True)
            out[freq_col] = out[col].astype("string").fillna("<missing>").map(freq).astype("float32")
            frequency_encoded.append(col)

        new_meta = ctx.storage.register(
            out,
            tenant_id=ctx.tenant.tenant_id,
            label=f"{meta.label} features",
            stage="features",
            parent_ids=[meta.id],
            created_by=self.name,
            provenance={
                "source_type": "agent",
                "transform": "datetime expansion + missing indicators + frequency encodings + preprocessing profile",
            },
        )
        payload = {
            "parent": meta.id,
            "target_preserved": target,
            "shape": list(new_meta.shape),
            "added_columns": [str(c) for c in out.columns if c not in df.columns],
            "datetime_features": datetime_features,
            "boolean_features": bool_features,
            "missing_indicators": missing_indicators,
            "frequency_encoded": frequency_encoded,
            "categorical_profile": categorical_profile,
            "model_time_encoding": {
                "low_cardinality": "one_hot",
                "medium_cardinality": "ordinal",
                "high_cardinality": "frequency_plus_ordinal_or_hashing",
                "free_text": "tfidf",
                "numeric": "median_impute_plus_scaling",
            },
        }
        return AgentResult(
            message=(
                "Feature engineering complete: "
                f"{out.shape[1]} columns with adaptive preprocessing profile."
            ),
            datasets={new_meta.id: new_meta},
            active_dataset_id=new_meta.id,
            artifacts=[
                ArtifactEnvelope(
                    kind="feature_report",
                    title="Adaptive feature engineering report",
                    dataset_id=new_meta.id,
                    payload=payload,
                )
            ],
        )

    def _categorical_profile(self, df: pd.DataFrame, target: str | None) -> dict[str, dict[str, object]]:
        profile: dict[str, dict[str, object]] = {}
        for col in df.select_dtypes(include=["object", "string", "category"]).columns:
            name = str(col)
            if target and name == target:
                continue
            nunique = int(df[col].nunique(dropna=True))
            avg_len = float(df[col].astype("string").dropna().str.len().mean() or 0)
            if self._looks_like_id(name, nunique, len(df)):
                strategy = "id_like_ignore_or_hash"
            elif avg_len >= self.text_avg_length_threshold:
                strategy = "tfidf"
            elif nunique <= 20:
                strategy = "one_hot_at_model_time"
            elif nunique <= self.high_cardinality_threshold:
                strategy = "ordinal_at_model_time"
            else:
                strategy = "frequency_encode"
            profile[name] = {
                "unique": nunique,
                "avg_length": round(avg_len, 2),
                "strategy": strategy,
            }
        return profile

    @staticmethod
    def _infer_target(df: pd.DataFrame, instruction: str) -> str | None:
        m = re.search(r"target\s*[:=]\s*([A-Za-z_][\w]*)", instruction or "")
        if m and m.group(1) in df.columns:
            return m.group(1)
        for candidate in (
            "target", "label", "y", "churn", "class", "diagnosis",
            "cancer", "outcome", "result", "risk", "disease",
        ):
            for col in df.columns:
                col_lower = str(col).lower()
                if col_lower == candidate or candidate in col_lower:
                    return str(col)
        return None

    @staticmethod
    def _try_datetime(series: pd.Series, name: str) -> pd.Series | None:
        name_lower = name.lower()
        if not any(token in name_lower for token in ("date", "time", "dt", "timestamp")):
            if not pd.api.types.is_datetime64_any_dtype(series):
                return None
        converted = pd.to_datetime(series, errors="coerce")
        if converted.notna().mean() < 0.7:
            return None
        return converted

    @staticmethod
    def _looks_like_id(name: str, unique_count: int, rows: int) -> bool:
        name_lower = name.lower()
        if name_lower in {"id", "uuid", "guid"} or name_lower.endswith("_id") or name_lower.endswith("id"):
            return True
        return rows > 0 and unique_count / rows > 0.9

    @staticmethod
    def _cyclic_sin(values: pd.Series, period: int):
        import numpy as np

        return np.sin(2 * np.pi * values.astype(float) / period).astype("float32")

    @staticmethod
    def _cyclic_cos(values: pd.Series, period: int):
        import numpy as np

        return np.cos(2 * np.pi * values.astype(float) / period).astype("float32")
