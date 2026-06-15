"""
DataCleaningAgent — Deterministic cleaning with production-grade prompt.

Handles: deduplication, missing value imputation (median/mode),
string trimming, datetime parsing, and data type normalization.
Results are written to the physically isolated 'data_cleaned' state slot.
"""
from __future__ import annotations

import pandas as pd

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope

CLEANING_PROMPT = """\
You are an expert data cleaning specialist. Your task is to prepare
raw data for downstream analysis by applying these deterministic operations:

1. **Deduplication**: Remove exact duplicate rows
2. **String Normalization**: Strip whitespace from text columns
3. **Missing Value Imputation**:
   - Categorical columns: fill with mode (most frequent value)
   - Numeric columns: fill with median (robust to outliers)
4. **DateTime Detection**: Auto-parse columns with 'date'/'time' in their name
5. **Type Optimization**: Downcast numeric types where possible

Report all changes made with before/after metrics.
"""


class DataCleaningAgent(BaseAgent):
    name = "data_cleaning_agent"
    description = "Deterministic cleaning: duplicates, missing values, object trimming."

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        meta, df = ctx.active_dataframe()
        await ctx.emit(f"Cleaning dataset `{meta.label}`.", agent_name=self.name)
        before = df.shape
        cleaned = df.copy()
        cleaned = cleaned.drop_duplicates()
        object_cols = cleaned.select_dtypes(include=["object", "string"]).columns
        for col in object_cols:
            cleaned[col] = cleaned[col].astype("string").str.strip()
            mode = cleaned[col].mode(dropna=True)
            if not mode.empty:
                cleaned[col] = cleaned[col].fillna(mode.iloc[0])
        numeric_cols = cleaned.select_dtypes(include=["number"]).columns
        for col in numeric_cols:
            cleaned[col] = cleaned[col].fillna(cleaned[col].median())
        datetime_candidates = [
            c for c in cleaned.columns if "date" in str(c).lower() or "time" in str(c).lower()
        ]
        for col in datetime_candidates:
            try:
                cleaned[col] = pd.to_datetime(cleaned[col], errors="ignore")
            except Exception:
                pass
        new_meta = ctx.storage.register(
            cleaned,
            tenant_id=ctx.tenant.tenant_id,
            label=f"{meta.label} cleaned",
            stage="cleaned",
            parent_ids=[meta.id],
            created_by=self.name,
            provenance={
                "source_type": "agent",
                "transform": "drop_duplicates + median/mode imputation + trim strings",
            },
        )
        metrics = {
            "before_shape": before,
            "after_shape": cleaned.shape,
            "removed_rows": int(before[0] - cleaned.shape[0]),
        }
        return AgentResult(
            message=f"Cleaned dataset. Removed {metrics['removed_rows']} duplicate rows.",
            datasets={new_meta.id: new_meta},
            active_dataset_id=new_meta.id,
            metrics=metrics,
            artifacts=[
                ArtifactEnvelope(
                    kind="cleaning_report",
                    title="Cleaning report",
                    dataset_id=new_meta.id,
                    payload=metrics,
                )
            ],
        )
