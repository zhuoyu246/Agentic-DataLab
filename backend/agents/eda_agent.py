"""
EDAAgent — Exploratory Data Analysis with production-grade profiling.

Generates comprehensive statistical profiles: shape, missing values,
cardinality, descriptive statistics, and correlation matrices.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.io as pio

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope

EDA_PROMPT = """\
You are an expert data analyst performing Exploratory Data Analysis (EDA).
Your task is to generate a comprehensive data profile including:

1. **Shape**: Number of rows and columns
2. **Missing Values**: Count and percentage per column
3. **Cardinality**: Number of unique values per column
4. **Statistical Summary**: describe() for all columns
5. **Correlations**: Pearson correlation matrix for numeric columns
6. **Data Quality Flags**: Identify columns with >50% missing, zero-variance, or high cardinality

Present findings in a structured, actionable format.
"""


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
        artifacts = [
            ArtifactEnvelope(
                kind="eda_report",
                title="Exploratory data analysis",
                dataset_id=meta.id,
                payload=summary,
            )
        ]
        artifacts.extend(self._eda_charts(meta.id, df, summary))
        return AgentResult(
            message=f"EDA complete for `{meta.label}`.",
            artifacts=artifacts,
        )

    def _eda_charts(self, dataset_id: str, df: pd.DataFrame, summary: dict) -> list[ArtifactEnvelope]:
        artifacts: list[ArtifactEnvelope] = []
        missing = df.isna().mean().sort_values(ascending=False)
        missing = missing[missing > 0].head(30)
        if not missing.empty:
            miss_df = missing.rename_axis("column").reset_index(name="missing_rate")
            artifacts.append(self._chart(dataset_id, "Missingness by Column", px.bar(miss_df, x="column", y="missing_rate")))

        cardinality = pd.Series(summary["cardinality"]).sort_values(ascending=False).head(30)
        if not cardinality.empty:
            card_df = cardinality.rename_axis("column").reset_index(name="unique_values")
            artifacts.append(self._chart(dataset_id, "Cardinality by Column", px.bar(card_df, x="column", y="unique_values")))

        numeric = df.select_dtypes(include=["number"])
        if not numeric.empty:
            col = str(numeric.columns[0])
            artifacts.append(self._chart(dataset_id, f"Distribution: {col}", px.histogram(df, x=col, nbins=40, marginal="box")))
        if numeric.shape[1] >= 2:
            corr = numeric.iloc[:, :30].corr(numeric_only=True).fillna(0)
            artifacts.append(self._chart(dataset_id, "Correlation Heatmap", px.imshow(corr, aspect="auto", color_continuous_scale="RdBu_r", zmin=-1, zmax=1)))
        return artifacts

    @staticmethod
    def _chart(dataset_id: str, title: str, fig) -> ArtifactEnvelope:
        fig.update_layout(template="plotly_white", title=title, margin=dict(l=42, r=24, t=48, b=38))
        return ArtifactEnvelope(
            kind="plotly_chart",
            title=title,
            dataset_id=dataset_id,
            payload={"plotly_json": pio.to_json(fig, validate=False, remove_uids=True)},
        )
