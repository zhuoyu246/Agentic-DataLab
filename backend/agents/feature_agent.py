from __future__ import annotations

import pandas as pd

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope


class FeatureEngineeringAgent(BaseAgent):
    name = "feature_engineering_agent"
    description = "Type-aware encoding and derived feature generation."

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        meta, df = ctx.active_dataframe()
        await ctx.emit("Creating model-ready features.", agent_name=self.name)
        out = df.copy()
        target = self._infer_target(out, instruction)
        low_card_cols = []
        for col in out.select_dtypes(include=["object", "string", "category"]).columns:
            if target and str(col) == target:
                continue
            if out[col].nunique(dropna=True) <= 20:
                low_card_cols.append(col)
        if low_card_cols:
            out = pd.get_dummies(out, columns=low_card_cols, dummy_na=True)
        for col in out.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
            if target and str(col) == target:
                continue
            out[f"{col}_year"] = out[col].dt.year
            out[f"{col}_month"] = out[col].dt.month
            out = out.drop(columns=[col])
        bool_cols = out.select_dtypes(include=["bool"]).columns
        for col in bool_cols:
            out[col] = out[col].astype(int)
        new_meta = ctx.storage.register(
            out,
            tenant_id=ctx.tenant.tenant_id,
            label=f"{meta.label} features",
            stage="features",
            parent_ids=[meta.id],
            created_by=self.name,
            provenance={
                "source_type": "agent",
                "transform": "one-hot low cardinality columns + datetime expansion",
            },
        )
        return AgentResult(
            message=f"Feature engineering complete: {out.shape[1]} columns.",
            datasets={new_meta.id: new_meta},
            active_dataset_id=new_meta.id,
            artifacts=[
                ArtifactEnvelope(
                    kind="feature_report",
                    title="Feature engineering report",
                    dataset_id=new_meta.id,
                    payload={
                        "parent": meta.id,
                        "target_preserved": target,
                        "encoded_columns": [str(c) for c in low_card_cols],
                        "shape": new_meta.shape,
                    },
                )
            ],
        )

    @staticmethod
    def _infer_target(df: pd.DataFrame, instruction: str) -> str | None:
        import re

        m = re.search(r"target\s*[:=]\s*([A-Za-z_][\w]*)", instruction or "")
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
        return None
