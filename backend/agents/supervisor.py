from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from agents.automl_agent import AutoMLAgent
from agents.base import AgentContext, AgentResult, BaseAgent
from agents.cleaning_agent import DataCleaningAgent
from agents.data_loader_agent import DataLoaderAgent
from agents.eda_agent import EDAAgent
from agents.feature_agent import FeatureEngineeringAgent
from agents.mlflow_agent import MLflowAgent
from agents.model_eval_agent import ModelEvaluationAgent
from agents.planner_agent import PlanModel, PlannerAgent, PlanStep
from agents.react_agent import ReActToolAgent
from agents.reflexion_agent import ReflexionAgent
from agents.sql_agent import SQLAgent
from agents.visualization_agent import VisualizationAgent
from agents.wrangling_agent import DataWranglingAgent
from schemas import AgentEvent, AgentRunStatus, ArtifactEnvelope, DatasetMeta


class SupervisorState(TypedDict, total=False):
    ctx: AgentContext
    prompt: str
    plan: PlanModel
    step_index: int
    max_steps: int
    reflexion_steps: int
    last_error: str | None
    final_message: str
    artifacts: list[ArtifactEnvelope]
    datasets: dict[str, DatasetMeta]
    active_dataset_id: str | None
    status: AgentRunStatus


class AgentSupervisor:
    """
    LangGraph supervisor with Plan-and-Execute + ReAct + Reflexion.

    The graph is intentionally small and hard bounded. Specialist agents own
    domain behavior; the supervisor only routes and enforces circuit breakers.
    """

    def __init__(
        self,
        planner: PlannerAgent,
        *,
        max_steps: int,
        max_reflexion_steps: int,
        agents: dict[str, BaseAgent] | None = None,
    ) -> None:
        self.planner = planner
        self.max_steps = max_steps
        self.max_reflexion_steps = max_reflexion_steps
        self.agents = agents or self.default_agents()
        self.reflexion = ReflexionAgent()
        self.react = ReActToolAgent(llm=self.planner.llm)
        self.graph = self._compile_graph()

    @staticmethod
    def default_agents() -> dict[str, BaseAgent]:
        return {
            "data_loader": DataLoaderAgent(),
            "sql": SQLAgent(),
            "wrangling": DataWranglingAgent(),
            "cleaning": DataCleaningAgent(),
            "eda": EDAAgent(),
            "visualization": VisualizationAgent(),
            "feature_engineering": FeatureEngineeringAgent(),
            "automl": AutoMLAgent(),
            "model_evaluation": ModelEvaluationAgent(),
            "mlflow": MLflowAgent(),
        }

    async def run(self, ctx: AgentContext) -> AgentResult:
        await ctx.events.publish(
            AgentEvent(
                session_id=ctx.session_id,
                run_id=ctx.run_id,
                type="status",
                status=AgentRunStatus.RUNNING,
                agent_name="supervisor",
                message="Supervisor started.",
            )
        )
        state: SupervisorState = {
            "ctx": ctx,
            "prompt": ctx.prompt,
            "step_index": 0,
            "max_steps": min(
                int(ctx.settings.get("recursion_limit", self.max_steps)),
                self.max_steps,
            ),
            "reflexion_steps": 0,
            "last_error": None,
            "artifacts": [],
            "datasets": dict(ctx.datasets),
            "active_dataset_id": ctx.active_dataset_id,
            "status": AgentRunStatus.RUNNING,
        }
        final = await self.graph.ainvoke(state)
        await ctx.events.publish(
            AgentEvent(
                session_id=ctx.session_id,
                run_id=ctx.run_id,
                type="done",
                status=final.get("status", AgentRunStatus.SUCCEEDED),
                agent_name="supervisor",
                message=final.get("final_message", "Run complete."),
            )
        )
        return AgentResult(
            message=final.get("final_message", "Run complete."),
            artifacts=final.get("artifacts", []),
            datasets=final.get("datasets", {}),
            active_dataset_id=final.get("active_dataset_id"),
            degraded=final.get("status") == AgentRunStatus.DEGRADED,
            error=final.get("last_error"),
        )

    def _compile_graph(self):
        workflow = StateGraph(SupervisorState)
        workflow.add_node("plan", self._node_plan)
        workflow.add_node("router", self._node_router)
        workflow.add_node("reflect", self._node_reflect)
        workflow.add_node("finish", self._node_finish)
        
        for name, agent in self.agents.items():
            workflow.add_node(name, self._create_agent_node(name, agent))
            workflow.add_conditional_edges(
                name,
                self._route_after_agent,
                {"reflect": "reflect", "router": "router", "finish": "finish"}
            )
            
        workflow.add_node("react_fallback", self._create_agent_node("react_fallback", self.react))
        workflow.add_conditional_edges(
            "react_fallback",
            self._route_after_agent,
            {"reflect": "reflect", "router": "router", "finish": "finish"}
        )

        workflow.set_entry_point("plan")
        workflow.add_edge("plan", "router")
        
        destinations = {name: name for name in self.agents.keys()}
        destinations["react_fallback"] = "react_fallback"
        destinations["finish"] = "finish"
        
        workflow.add_conditional_edges("router", self._route_from_router, destinations)
        workflow.add_conditional_edges(
            "reflect",
            self._route_after_reflect,
            {"router": "router", "finish": "finish"}
        )
        
        workflow.add_edge("finish", END)
        return workflow.compile(name="agentic_datalab_supervisor")

    async def _node_plan(self, state: SupervisorState) -> SupervisorState:
        ctx = state["ctx"]
        await ctx.emit("Planning multi-agent workflow.", agent_name="planner_agent")
        plan = await self.planner.plan(ctx, state["prompt"])
        if len(plan.steps) > state["max_steps"]:
            plan = PlanModel(goal=plan.goal, steps=plan.steps[: state["max_steps"]])
            await ctx.emit(
                "Plan exceeded max steps and was truncated.",
                agent_name="supervisor",
                event_type="warning",
            )
        return {**state, "plan": plan, "final_message": ""}

    async def _node_router(self, state: SupervisorState) -> SupervisorState:
        return state

    def _create_agent_node(self, agent_name: str, agent: BaseAgent):
        async def _node(state: SupervisorState) -> SupervisorState:
            ctx = state["ctx"]
            plan = state.get("plan") or PlanModel(goal=state["prompt"], steps=[])
            step_index = int(state.get("step_index", 0))
            if step_index >= len(plan.steps):
                return state
            step = plan.steps[step_index]
            
            await ctx.events.publish(
                AgentEvent(
                    session_id=ctx.session_id,
                    run_id=ctx.run_id,
                    type="agent_start",
                    status=AgentRunStatus.RUNNING,
                    agent_name=agent_name,
                    message=step.instruction,
                    payload={"step_index": step_index, "total": len(plan.steps)},
                )
            )
            try:
                result = await agent.run(ctx, step.instruction)
                merged_datasets = {**state.get("datasets", {}), **result.datasets}
                ctx.datasets.update(result.datasets)
                if result.active_dataset_id:
                    ctx.active_dataset_id = result.active_dataset_id
                artifacts = [*state.get("artifacts", []), *result.artifacts]
                await ctx.events.publish(
                    AgentEvent(
                        session_id=ctx.session_id,
                        run_id=ctx.run_id,
                        type="agent_end",
                        status=AgentRunStatus.DEGRADED if result.degraded else AgentRunStatus.SUCCEEDED,
                        agent_name=agent_name,
                        message=result.message,
                        payload={"metrics": result.metrics},
                    )
                )
                for artifact in result.artifacts:
                    await ctx.events.publish(
                        AgentEvent(
                            session_id=ctx.session_id,
                            run_id=ctx.run_id,
                            type="artifact",
                            status=AgentRunStatus.RUNNING,
                            agent_name=agent_name,
                            message=artifact.title,
                            payload=artifact.model_dump(mode="json"),
                        )
                    )
                final_message = self._append_message(state.get("final_message", ""), result.message)
                return {
                    **state,
                    "step_index": step_index + 1,
                    "datasets": merged_datasets,
                    "active_dataset_id": result.active_dataset_id or state.get("active_dataset_id"),
                    "artifacts": artifacts,
                    "last_error": result.error,
                    "final_message": final_message,
                    "status": AgentRunStatus.DEGRADED if result.degraded else AgentRunStatus.RUNNING,
                }
            except Exception as exc:
                await ctx.events.publish(
                    AgentEvent(
                        session_id=ctx.session_id,
                        run_id=ctx.run_id,
                        type="error",
                        status=AgentRunStatus.FAILED,
                        agent_name=agent_name,
                        message=str(exc),
                    )
                )
                return {
                    **state,
                    "last_error": f"{agent_name}: {exc}",
                    "status": AgentRunStatus.DEGRADED,
                }
        return _node

    async def _node_reflect(self, state: SupervisorState) -> SupervisorState:
        ctx = state["ctx"]
        error = state.get("last_error") or "unknown error"
        reflection = await self.reflexion.run(ctx, error)
        plan = state.get("plan") or PlanModel(goal=state["prompt"], steps=[])
        step_index = int(state.get("step_index", 0))
        if step_index < len(plan.steps):
            current = plan.steps[step_index]
            revised = PlanStep(agent=current.agent, instruction=reflection.message)
            steps = list(plan.steps)
            steps[step_index] = revised
            plan = PlanModel(goal=plan.goal, steps=steps)
        return {
            **state,
            "plan": plan,
            "reflexion_steps": int(state.get("reflexion_steps", 0)) + 1,
            "last_error": None,
        }

    async def _node_finish(self, state: SupervisorState) -> SupervisorState:
        status = state.get("status", AgentRunStatus.SUCCEEDED)
        if state.get("last_error"):
            status = AgentRunStatus.DEGRADED
        elif status == AgentRunStatus.RUNNING:
            status = AgentRunStatus.SUCCEEDED
        message = state.get("final_message") or "No specialist agent produced output."
        return {**state, "status": status, "final_message": message}

    def _route_from_router(self, state: SupervisorState) -> str:
        plan = state.get("plan") or PlanModel(goal=state.get("prompt", ""), steps=[])
        step_index = int(state.get("step_index", 0))
        if step_index >= len(plan.steps):
            return "finish"
        if step_index >= int(state.get("max_steps", self.max_steps)):
            return "finish"
        
        step = plan.steps[step_index]
        if step.agent in self.agents:
            return step.agent
        return "react_fallback"

    def _route_after_agent(self, state: SupervisorState) -> str:
        if state.get("last_error"):
            if int(state.get("reflexion_steps", 0)) < self.max_reflexion_steps:
                return "reflect"
            return "finish"
        return "router"

    def _route_after_reflect(self, state: SupervisorState) -> str:
        if int(state.get("step_index", 0)) >= int(state.get("max_steps", self.max_steps)):
            return "finish"
        return "router"

    @staticmethod
    def _append_message(existing: str, line: str) -> str:
        if not existing:
            return line
        return existing.rstrip() + "\n" + line

