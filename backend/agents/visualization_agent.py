from __future__ import annotations

import plotly.express as px
import plotly.io as pio
import plotly.graph_objects as go

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope


class VisualizationAgent(BaseAgent):
    name = "visualization_agent"
    description = "Plotly chart generation with fallback chart degradation."

    max_chart_rows = 2_000
    max_categories = 12
    max_payload_chars = 350_000

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        meta, df = ctx.active_dataframe()
        await ctx.emit("Building Plotly chart.", agent_name=self.name)
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
        numeric_cols = [str(c) for c in frame.select_dtypes(include=["number"]).columns]
        categorical_cols = [str(c) for c in frame.columns if str(c) not in numeric_cols]
        low_card_color = self._pick_low_cardinality_column(frame, categorical_cols)
        try:
            if len(numeric_cols) >= 2 and (
                "scatter" in instruction.lower() or "关系" in instruction
            ):
                fig = px.scatter(
                    frame,
                    x=numeric_cols[0],
                    y=numeric_cols[1],
                    color=low_card_color,
                    render_mode="webgl" if len(frame) > 1_000 else "auto",
                )
            elif numeric_cols:
                fig = px.histogram(
                    frame,
                    x=numeric_cols[0],
                    color=low_card_color,
                    nbins=min(40, max(10, int(len(frame) ** 0.5))),
                )
            else:
                cat = categorical_cols[0]
                counts = frame[cat].astype("string").fillna("<missing>").value_counts().head(20).reset_index()
                counts.columns = [cat, "count"]
                fig = px.bar(counts, x=categorical_cols[0], y="count")
            fig.update_layout(template="plotly_white", margin=dict(l=24, r=18, t=36, b=28))
            payload = pio.to_json(fig, validate=False, remove_uids=True)
            payload, clipped = self._enforce_payload_budget(payload)
            degraded = False
            message = "Chart generated."
            if clipped:
                degraded = True
                message = "Chart generated with payload budget clipping."
        except Exception as exc:
            payload = self._fallback_chart_payload(df)
            degraded = True
            message = f"Primary chart failed; fallback chart rendered: {exc}"
        return AgentResult(
            message=message,
            degraded=degraded,
            artifacts=[
                ArtifactEnvelope(
                    kind="plotly_chart",
                    title="Visualization",
                    dataset_id=meta.id,
                    payload={
                        "plotly_json": payload,
                        "rows_used": int(len(frame)),
                        "source_rows": int(len(df)),
                        "source_columns": int(len(df.columns)),
                    },
                    degraded=degraded,
                )
            ],
        )

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

    def _enforce_payload_budget(self, payload: str) -> tuple[str, bool]:
        if len(payload) <= self.max_payload_chars:
            return payload, False
        fig = go.Figure()
        fig.add_annotation(
            text="Chart exceeded server payload budget; request a narrower chart.",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        fig.update_layout(template="plotly_white", xaxis={"visible": False}, yaxis={"visible": False})
        return pio.to_json(fig, validate=False, remove_uids=True), True

    def _fallback_chart_payload(self, df) -> str:
        numeric_cols = [str(c) for c in df.select_dtypes(include=["number"]).columns]
        if numeric_cols:
            series = df[numeric_cols[0]].dropna().head(100)
            fallback = series.reset_index()
            fig = px.line(fallback, x="index", y=numeric_cols[0])
        else:
            col = str(df.columns[0])
            counts = df[col].astype("string").fillna("<missing>").value_counts().head(20).reset_index()
            counts.columns = [col, "count"]
            fig = px.bar(counts, x=col, y="count")
        fig.update_layout(template="plotly_white", margin=dict(l=24, r=18, t=36, b=28))
        payload = pio.to_json(fig, validate=False, remove_uids=True)
        return payload[: self.max_payload_chars]
