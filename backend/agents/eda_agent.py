from __future__ import annotations

import pandas as pd

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope


class EDAAgent(BaseAgent):
    name = "eda_agent"
    description = "EDA summaries, missingness, cardinality and correlations."

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        meta, df = ctx.active_dataframe()
        await ctx.emit(f"Profiling `{meta.label}`.", agent_name=self.name)
        numeric = df.select_dtypes(include=["number"])
        summary = {
            "shape": [int(df.shape[0]), int(df.shape[1])],
            "missing": {str(k): int(v) for k, v in df.isna().sum().items()},
            "cardinality": {str(c): int(df[c].nunique(dropna=True)) for c in df.columns},
            "describe": df.describe(include="all").fillna("").astype(str).to_dict(),
        }
        if not numeric.empty:
            corr = numeric.corr(numeric_only=True).fillna(0)
            summary["correlation"] = corr.round(4).to_dict()
        return AgentResult(
            message=f"EDA complete for `{meta.label}`.",
            artifacts=[
                ArtifactEnvelope(
                    kind="eda_report",
                    title="Exploratory data analysis",
                    dataset_id=meta.id,
                    payload=summary,
                )
            ],
        )

