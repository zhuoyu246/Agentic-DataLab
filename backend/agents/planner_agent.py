"""
PlannerAgent — Industrial-Grade Plan-and-Execute Macro Planner.

Architecture (Plan-and-Execute Paradigm):
The Planner is the strategic brain that NEVER touches tools. It only
decomposes user goals into a sequence of atomic, executable steps
assigned to specific specialist agents.

Academic reference: "Plan-and-Solve Prompting" (Wang et al., 2023)

Key features:
- Production-grade system prompt with strict agent capability boundaries
- Replanning support: when a worker fails, the planner can revise remaining steps
- Heuristic fallback: when LLM is unavailable, keyword-based plan generation
- Max 12 steps hard cap to prevent runaway planning
"""
from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel, Field

from agents.base import AgentContext, AgentResult, BaseAgent
from core.llm import VLLMClient


class PlanStep(BaseModel):
    agent: Literal[
        "data_loader",
        "sql",
        "wrangling",
        "cleaning",
        "eda",
        "visualization",
        "feature_engineering",
        "automl",
        "model_evaluation",
        "mlflow",
    ]
    instruction: str


class PlanModel(BaseModel):
    goal: str
    steps: list[PlanStep] = Field(default_factory=list, max_length=12)


# ---------------------------------------------------------------------------
# Production-Grade Plan-and-Execute System Prompt
# ---------------------------------------------------------------------------
PLANNER_SYSTEM_PROMPT = """\
You are an elite Enterprise Data Science Architect and Macro Planner.

## ROLE AND MISSION
Your sole job is to decompose the user's analytical goal into a sequence of
executable steps. You are a STRATEGIST — you NEVER execute tools yourself.
Each step must be assigned to exactly one specialist agent.

## AVAILABLE AGENTS AND THEIR CAPABILITIES
- data_loader: Strictly for loading local CSV/Excel/Parquet files into the workspace.
  DO NOT use if a dataset is already active, unless the user provides a new file path.
- sql: For querying relational databases (PostgreSQL/MySQL). Generates and executes
  guarded SQL with Row-Level Security (RLS) and HITL enforcement for write operations.
- cleaning: Imputation of missing values, deduplication, and data type casting.
  Deterministic operations only — no LLM inference during cleaning.
- wrangling: Merge, join, concat, aggregate, and reshape datasets.
  Handles multi-dataset operations and type normalization.
- eda: Exploratory Data Analysis. Calculates statistics, distributions,
  missingness, cardinality, and correlations. Produces structured EDA reports.
- visualization: Generating interactive business intelligence charts (Plotly).
  Auto-selects chart type based on data characteristics.
- feature_engineering: One-hot encoding, scaling, binning, datetime expansion,
  and preprocessing for ML pipelines. Preserves target column integrity.
- automl: Training machine learning models (H2O AutoML with sklearn fallback).
  Automatically handles algorithm selection, hyperparameter tuning, and model logging.
- model_evaluation: Extracting model diagnostics and generating structured
  evaluation metrics (confusion matrix, ROC curve, feature importance).
- mlflow: Experiment tracking, run searching, and model registry operations.

## PLANNING RULES
1. ONLY use the exact agent names listed above. Any other name will cause a crash.
2. If a dataset is already active, assume it is ready for downstream tasks.
   Do NOT call data_loader redundantly.
3. For ML workflows, ensure the pipeline follows: cleaning → feature_engineering → automl → model_evaluation
4. Each step instruction must be self-contained and unambiguous.
5. Keep the plan minimal — do NOT add superfluous steps.
6. Return ONLY strict JSON matching the provided schema. No markdown, no explanation.

## OUTPUT FORMAT
Return a JSON object with:
- "goal": the user's original intent (string)
- "steps": array of objects, each with "agent" (string) and "instruction" (string)
"""

REPLAN_PROMPT = """\
## REPLANNING REQUIRED
The previous execution encountered an error at step {step_index}:
Agent: {failed_agent}
Error: {error_message}

Please revise the REMAINING steps of the plan (starting from step {step_index}).
You may:
1. Retry the same agent with a modified instruction
2. Skip the failed step and adjust downstream steps
3. Insert a new preparatory step before retrying

The steps that already succeeded should NOT be changed.
Previous successful steps: {completed_steps}
"""


class PlannerAgent(BaseAgent):
    """
    Plan-and-Execute macro planner with LLM-powered decomposition
    and keyword-based heuristic fallback.
    """
    name = "planner_agent"
    description = "Plan-and-Execute macro planner. Decomposes goals into agent-executable DAG steps."

    def __init__(self, llm: VLLMClient | None = None) -> None:
        self.llm = llm

    async def plan(self, ctx: AgentContext, prompt: str) -> PlanModel:
        """
        Generate an execution plan using LLM or heuristic fallback.

        Strategy:
        1. Try LLM-powered planning with structured JSON output
        2. If LLM is unavailable or fails, degrade to heuristic keyword matching
        """
        if (
            self.llm is not None
            and ctx.settings.get("use_large_planner", True)
            and await self.llm.is_available()
        ):
            schema_hint = PlanModel.model_json_schema()

            history_text = "\n".join(f"{m['role']}: {m['content']}" for m in ctx.history[-6:])
            context_str = f"Chat History:\n{history_text}\n\n" if history_text else ""

            dataset_info = "No dataset currently active."
            if ctx.active_dataset_id and ctx.active_dataset_id in ctx.datasets:
                meta = ctx.datasets[ctx.active_dataset_id]
                dataset_info = f"Active Dataset: {meta.label} (stage: {meta.stage})"

            try:
                result = await asyncio.wait_for(
                    self.llm.complete_json(
                        [
                            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": (
                                    f"Schema: {schema_hint}\n\n"
                                    f"{context_str}"
                                    f"Workspace Status:\n{dataset_info}\n\n"
                                    f"Current User goal: {prompt}"
                                ),
                            },
                        ],
                        PlanModel,
                        retries=1,
                    ),
                    timeout=float(ctx.settings.get("planner_timeout_seconds", 6)),
                )
                if result.ok and result.data and result.data.steps:
                    return result.data
            except Exception as exc:
                await ctx.emit(
                    f"vLLM planner degraded to heuristic planner: {exc}",
                    agent_name=self.name,
                    event_type="warning",
                )
        return self._heuristic_plan(prompt, has_dataset=bool(ctx.datasets))

    async def replan(
        self,
        ctx: AgentContext,
        original_plan: PlanModel,
        step_index: int,
        error: str,
    ) -> PlanModel:
        """
        Replanning: revise remaining steps after a failure.

        This is a key feature of the Plan-and-Execute paradigm —
        the planner can dynamically adapt the plan based on runtime feedback.
        """
        if self.llm is None or not await self.llm.is_available():
            return original_plan

        completed = [
            f"Step {i}: {s.agent} — {s.instruction[:80]}"
            for i, s in enumerate(original_plan.steps[:step_index])
        ]

        try:
            result = await asyncio.wait_for(
                self.llm.complete_json(
                    [
                        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": REPLAN_PROMPT.format(
                                step_index=step_index,
                                failed_agent=original_plan.steps[step_index].agent if step_index < len(original_plan.steps) else "unknown",
                                error_message=error[:500],
                                completed_steps="\n".join(completed) or "None",
                            ),
                        },
                    ],
                    PlanModel,
                    retries=1,
                ),
                timeout=6.0,
            )
            if result.ok and result.data:
                # Merge: keep completed steps + revised remaining steps
                revised = PlanModel(
                    goal=original_plan.goal,
                    steps=list(original_plan.steps[:step_index]) + result.data.steps,
                )
                return revised
        except Exception:
            pass
        return original_plan

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        plan = await self.plan(ctx, instruction)
        return AgentResult(message=plan.model_dump_json())

    def _heuristic_plan(self, prompt: str, *, has_dataset: bool) -> PlanModel:
        """
        Keyword-based fallback planner for when LLM is unavailable.

        This implements a deterministic DFA-like decision tree:
        keywords → agent mapping, ensuring the system never fully stops.
        """
        text = (prompt or "").lower()
        steps: list[PlanStep] = []
        if any(w in text for w in ["sql", "query", "database", "表", "数据库"]):
            steps.append(PlanStep(agent="sql", instruction=prompt))
        if not has_dataset and any(w in text for w in ["load", "upload", "读取", "加载"]):
            steps.append(PlanStep(agent="data_loader", instruction=prompt))
        if any(w in text for w in ["clean", "missing", "duplicate", "清洗", "缺失"]):
            steps.append(PlanStep(agent="cleaning", instruction=prompt))
        if any(w in text for w in ["merge", "join", "concat", "wrangle", "合并"]):
            steps.append(PlanStep(agent="wrangling", instruction=prompt))
        if any(w in text for w in ["feature", "encode", "特征"]):
            steps.append(PlanStep(agent="feature_engineering", instruction=prompt))
        if any(w in text for w in ["eda", "describe", "summary", "分析", "探索"]):
            steps.append(PlanStep(agent="eda", instruction=prompt))
        if any(w in text for w in ["chart", "plot", "visual", "图", "可视化"]):
            steps.append(PlanStep(agent="visualization", instruction=prompt))
        if any(w in text for w in ["train", "automl", "model", "预测", "建模"]):
            if not any(s.agent == "cleaning" for s in steps) and has_dataset:
                steps.append(PlanStep(agent="cleaning", instruction="Prepare data for modeling."))
            steps.append(PlanStep(agent="feature_engineering", instruction=prompt))
            steps.append(PlanStep(agent="automl", instruction=prompt))
            steps.append(PlanStep(agent="model_evaluation", instruction=prompt))
        if any(w in text for w in ["mlflow", "experiment", "run id", "实验"]):
            steps.append(PlanStep(agent="mlflow", instruction=prompt))
        if not steps:
            if has_dataset:
                steps = [
                    PlanStep(agent="eda", instruction=prompt),
                    PlanStep(agent="visualization", instruction=prompt),
                ]
            else:
                steps = [PlanStep(agent="data_loader", instruction=prompt)]
        return PlanModel(goal=prompt, steps=steps[:12])
