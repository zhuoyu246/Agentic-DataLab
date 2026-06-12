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


class PlannerAgent(BaseAgent):
    name = "planner_agent"
    description = "Plan-and-Execute macro planner."

    def __init__(self, llm: VLLMClient | None = None) -> None:
        self.llm = llm

    async def plan(self, ctx: AgentContext, prompt: str) -> PlanModel:
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
                            {
                                "role": "system",
                                "content": (
                                    "You are an elite Enterprise Data Science Architect and Macro Planner. "
                                    "Your job is to decompose the user's goal into a sequence of executable steps using ONLY the available agents.\n\n"
                                    "AVAILABLE AGENTS AND THEIR CAPABILITIES:\n"
                                    "- data_loader: Strictly for loading local CSV/Excel files into the workspace. DO NOT use if a dataset is already active, unless the user provides a new file path.\n"
                                    "- sql: For querying relational databases (PostgreSQL/MySQL).\n"
                                    "- cleaning: Imputation of missing values, deduplication, and data type casting.\n"
                                    "- eda: Exploratory Data Analysis. Calculates statistics, distributions, and data profiles.\n"
                                    "- visualization: Generating interactive business intelligence charts (Plotly).\n"
                                    "- feature_engineering: One-hot encoding, scaling, binning, and preprocessing for ML.\n"
                                    "- automl: Training machine learning models (H2O/Sklearn). Automatically handles algorithms.\n"
                                    "- model_evaluation: Extracting model diagnostics and generating evaluation metrics.\n"
                                    "- mlflow: Experiment tracking and run logging.\n\n"
                                    "RULES:\n"
                                    "1. ONLY use the exact agent names listed above.\n"
                                    "2. If a dataset is active, assume it is ready for downstream tasks. Do NOT call data_loader redundantly.\n"
                                    "3. Return ONLY strict JSON matching the provided schema."
                                ),
                            },
                            {
                                "role": "user",
                                "content": f"Schema: {schema_hint}\n\n{context_str}Workspace Status:\n{dataset_info}\n\nCurrent User goal: {prompt}",
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

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        plan = await self.plan(ctx, instruction)
        return AgentResult(message=plan.model_dump_json())

    def _heuristic_plan(self, prompt: str, *, has_dataset: bool) -> PlanModel:
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
