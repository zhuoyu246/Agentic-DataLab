"""
VisualizationAgent - adaptive Plotly chart suite generation.

Instead of returning a single generic chart, this agent emits a compact suite
of useful charts selected from the data shape: distributions, categorical
bars, scatter/box plots, correlations, missingness, and time trends.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope

VISUALIZATION_PROMPT = """\
Generate a compact, useful chart suite:
- numeric distributions
- categorical frequency bars
- scatter/relationship views
- box plots by category
- correlation heatmaps
- missingness/data quality charts
- time-series trend charts when datetime columns exist
Keep each Plotly payload small and degrade gracefully.
"""


class VisualizationAgent(BaseAgent):
    name = "visualization_agent"
    description = "Adaptive Plotly chart suite generation."

    max_chart_rows = 2_000
    max_categories = 15
    max_payload_chars = 350_000

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        meta, df = ctx.active_dataframe()
        await ctx.emit("Building adaptive Plotly chart suite.", agent_name=self.name)
        if df.empty:
            return AgentResult(
                message="Dataset is empty; no chart can be generated.",
                degraded=True,
                artifacts=[
                    ArtifactEnvelope(
                        kind="plotly_chart",
                        title="Visualization unavailable",
                        dataset_id=meta.id,
                        payload={"reason": "empty_dataset"},
                        degraded=True,
                    )
                ],
            )

        frame = self._sample_frame(df)
        artifacts: list[ArtifactEnvelope] = []
        for title, fig in self._build_suite(frame, instruction):
            payload, clipped = self._figure_payload(fig)
            artifacts.append(
                ArtifactEnvelope(
                    kind="plotly_chart",
                    title=title,
                    dataset_id=meta.id,
                    payload={
                        "plotly_json": payload,
                        "rows_used": int(len(frame)),
                        "source_rows": int(len(df)),
                        "source_columns": int(len(df.columns)),
                    },
                    degraded=clipped,
                )
            )
        if not artifacts:
            payload, clipped = self._figure_payload(self._fallback_chart(df))
            artifacts.append(
                ArtifactEnvelope(
                    kind="plotly_chart",
                    title="Fallback Visualization",
                    dataset_id=meta.id,
                    payload={"plotly_json": payload},
                    degraded=clipped,
                )
            )
        return AgentResult(
            message=f"Generated {len(artifacts)} visualization charts.",
            degraded=any(a.degraded for a in artifacts),
            artifacts=artifacts,
        )

    def _build_suite(self, df: pd.DataFrame, instruction: str):
        charts: list[tuple[str, go.Figure]] = []
        numeric_cols = [str(c) for c in df.select_dtypes(include=["number"]).columns]
        datetime_cols = self._datetime_columns(df)
        categorical_cols = [
            str(c)
            for c in df.columns
            if str(c) not in numeric_cols and str(c) not in datetime_cols
        ]
        low_card = self._pick_low_cardinality_column(df, categorical_cols)
        text = (instruction or "").lower()

        if numeric_cols:
            col = self._requested_column(text, numeric_cols) or numeric_cols[0]
            charts.append((f"Distribution: {col}", px.histogram(df, x=col, color=low_card, marginal="box", nbins=min(50, max(10, int(len(df) ** 0.5))))))

        if categorical_cols:
            cat = self._requested_column(text, categorical_cols) or low_card or categorical_cols[0]
            counts = df[cat].astype("string").fillna("<missing>").value_counts().head(self.max_categories).reset_index()
            counts.columns = [cat, "count"]
            charts.append((f"Category Frequency: {cat}", px.bar(counts, x=cat, y="count")))

        if len(numeric_cols) >= 2:
            x_col = numeric_cols[0]
            y_col = numeric_cols[1]
            charts.append((f"Relationship: {x_col} vs {y_col}", px.scatter(df, x=x_col, y=y_col, color=low_card, render_mode="webgl" if len(df) > 1_000 else "auto")))

        if numeric_cols and low_card:
            charts.append((f"Box Plot: {numeric_cols[0]} by {low_card}", px.box(df, x=low_card, y=numeric_cols[0], color=low_card)))

        if len(numeric_cols) >= 2:
            corr = df[numeric_cols[:30]].corr(numeric_only=True).fillna(0)
            charts.append(("Correlation Heatmap", px.imshow(corr, aspect="auto", color_continuous_scale="RdBu_r", zmin=-1, zmax=1)))

        missing = df.isna().mean().sort_values(ascending=False)
        missing = missing[missing > 0].head(30)
        if not missing.empty:
            miss_df = missing.rename_axis("column").reset_index(name="missing_rate")
            charts.append(("Missingness by Column", px.bar(miss_df, x="column", y="missing_rate")))

        if datetime_cols and numeric_cols:
            dt_col = datetime_cols[0]
            temp = df[[dt_col, numeric_cols[0]]].copy()
            temp[dt_col] = pd.to_datetime(temp[dt_col], errors="coerce")
            temp = temp.dropna().sort_values(dt_col)
            if not temp.empty:
                grouped = temp.set_index(dt_col).resample(self._time_freq(temp[dt_col])).mean(numeric_only=True).reset_index()
                charts.append((f"Time Trend: {numeric_cols[0]}", px.line(grouped, x=dt_col, y=numeric_cols[0])))

        return charts[:7]

    def _sample_frame(self, df):
        if len(df) <= self.max_chart_rows:
            return df.copy()
        return df.sample(self.max_chart_rows, random_state=42).copy()

    def _pick_low_cardinality_column(self, df, categorical_cols: list[str]) -> str | None:
        best: tuple[int, str] | None = None
        for col in categorical_cols:
            name = col.lower()
            if name.endswith("id") or name in {"id", "uuid", "guid", "customerid"}:
                continue
            try:
                n = int(df[col].nunique(dropna=True))
            except Exception:
                continue
            if 1 < n <= self.max_categories:
                if best is None or n < best[0]:
                    best = (n, col)
        return best[1] if best else None

    @staticmethod
    def _requested_column(text: str, columns: list[str]) -> str | None:
        for col in columns:
            if col.lower() in text:
                return col
        return None

    @staticmethod
    def _datetime_columns(df: pd.DataFrame) -> list[str]:
        out: list[str] = []
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                out.append(str(col))
                continue
            name = str(col).lower()
            if any(token in name for token in ("date", "time", "timestamp")):
                converted = pd.to_datetime(df[col], errors="coerce")
                if converted.notna().mean() >= 0.7:
                    out.append(str(col))
        return out

    @staticmethod
    def _time_freq(series: pd.Series) -> str:
        span_days = max((series.max() - series.min()).days, 1)
        if span_days > 730:
            return "ME"
        if span_days > 90:
            return "W"
        return "D"

    def _figure_payload(self, fig) -> tuple[str, bool]:
        fig.update_layout(template="plotly_white", margin=dict(l=42, r=24, t=48, b=38))
        payload = pio.to_json(fig, validate=False, remove_uids=True)
        if len(payload) <= self.max_payload_chars:
            return payload, False
        fallback = go.Figure()
        fallback.add_annotation(
            text="Chart exceeded server payload budget; request a narrower chart.",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        fallback.update_layout(template="plotly_white", xaxis={"visible": False}, yaxis={"visible": False})
        return pio.to_json(fallback, validate=False, remove_uids=True), True

    def _fallback_chart(self, df) -> go.Figure:
        numeric_cols = [str(c) for c in df.select_dtypes(include=["number"]).columns]
        if numeric_cols:
            series = df[numeric_cols[0]].dropna().head(100)
            fallback = series.reset_index()
            return px.line(fallback, x="index", y=numeric_cols[0])
        col = str(df.columns[0])
        counts = df[col].astype("string").fillna("<missing>").value_counts().head(20).reset_index()
        counts.columns = [col, "count"]
        return px.bar(counts, x=col, y="count")
