from __future__ import annotations

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope


class MLflowAgent(BaseAgent):
    name = "mlflow_agent"
    description = "Search experiments/runs and expose model registry operations."

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        await ctx.emit("Querying MLflow tracking store.", agent_name=self.name)
        try:
            import mlflow

            mlflow.set_tracking_uri(ctx.settings.get("mlflow_tracking_uri"))
            experiments = mlflow.search_experiments()
            payload = {
                "experiments": [
                    {
                        "experiment_id": e.experiment_id,
                        "name": e.name,
                        "artifact_location": e.artifact_location,
                        "lifecycle_stage": e.lifecycle_stage,
                    }
                    for e in experiments
                ]
            }
            return AgentResult(
                message=f"Found {len(experiments)} MLflow experiment(s).",
                artifacts=[
                    ArtifactEnvelope(
                        kind="mlflow",
                        title="MLflow experiments",
                        payload=payload,
                    )
                ],
            )
        except Exception as exc:
            return AgentResult(
                message=f"MLflow unavailable: {exc}",
                degraded=True,
                error=str(exc),
            )

