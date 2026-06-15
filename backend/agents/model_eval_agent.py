"""
ModelEvaluationAgent — Structured evaluation report generation.

Collects model metrics from AutoML runs and generates actionable
evaluation artifacts with interpretation guidance.
"""
from __future__ import annotations

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope

MODEL_EVAL_PROMPT = """\
You are an expert ML model evaluation specialist. Your task is to:

1. **Collect Metrics**: Gather accuracy/R², precision, recall, F1, AUC-ROC
2. **Generate Diagnostics**: Confusion matrix, ROC curve, residual plots
3. **Feature Importance**: Rank features by contribution to predictions
4. **Interpretation**: Provide actionable insights:
   - Is the model overfitting or underfitting?
   - Which features are most/least predictive?
   - What are the recommended next steps (more data, feature engineering, etc.)?
5. **Cross-Reference**: Link metrics to MLflow run IDs for reproducibility
"""


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
