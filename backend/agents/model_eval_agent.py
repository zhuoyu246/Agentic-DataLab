from __future__ import annotations

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope


class ModelEvaluationAgent(BaseAgent):
    name = "model_evaluation_agent"
    description = "Collect latest model metrics and generate evaluation artifacts."

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        await ctx.emit("Collecting model evaluation artifacts.", agent_name=self.name)
        return AgentResult(
            message="Model evaluation summary is available when AutoML logs metrics.",
            artifacts=[
                ArtifactEnvelope(
                    kind="evaluation",
                    title="Evaluation summary",
                    payload={
                        "note": "Evaluation metrics are attached to model_info and MLflow runs.",
                        "run_id": ctx.run_id,
                    },
                )
            ],
        )

