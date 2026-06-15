"""
ReActToolAgent — Industrial-Grade ReAct Loop with Circuit Breaker.

Academic reference: "ReAct: Synergizing Reasoning and Acting" (Yao et al., 2023)

Features:
- Thought → Action → Observation iterative loop
- Hard circuit breaker (max 5 iterations)
- MCP governance integration
- Scratchpad-based memory
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from agents.base import AgentContext, AgentResult, BaseAgent
from core.llm import VLLMClient

ToolCallable = Callable[[AgentContext, str], Awaitable[AgentResult]]
MAX_REACT_ITERATIONS: int = 5


class ReActAction(BaseModel):
    thought: str = Field(description="Your step-by-step reasoning about what to do next.")
    action: str | None = Field(description="Name of the tool to invoke. Null if is_final is True.")
    action_input: str | None = Field(description="The input argument string for the selected tool.")
    is_final: bool = Field(description="Set to true when goal is achieved or no tool fits.")
    final_answer: str | None = Field(description="The final consolidated answer or summary.")


class ReActState(TypedDict, total=False):
    ctx: AgentContext
    instruction: str
    messages: list[dict[str, str]]
    iterations: int
    final_result: AgentResult | None


REACT_SYSTEM_PROMPT = """\
You are a ReAct-based AI assistant that solves complex tasks through iterative
reasoning and tool usage. Follow the Thought-Action-Observation loop strictly.

## AVAILABLE TOOLS
{tool_descriptions}

## EXECUTION FORMAT
Output a JSON object with these fields:
- "thought": Your detailed reasoning about the current situation and what to do next.
  Analyze previous observations, identify missing information, explain WHY you chose the next action.
- "action": Exact tool name from the list above. Null only when providing final answer.
- "action_input": The input string for the tool. Be specific and precise.
- "is_final": True ONLY when you have sufficient information for a confident final answer.
- "final_answer": Your consolidated final answer. Required when is_final is true.

## CRITICAL RULES
1. ALWAYS start with a thought that analyzes the current state.
2. If a tool returns an error, reflect on WHY and try a different approach.
3. Do NOT repeat the same action with the same input — this indicates a loop.
4. You have maximum {max_iterations} iterations. Use them wisely.
5. If no tool can solve the problem, set is_final=true and explain in final_answer.
6. Return ONLY valid JSON. No markdown, no extra text.
"""


class ReActToolAgent(BaseAgent):
    name = "react_tool_agent"
    description = "LangGraph ReAct loop with Thought-Action-Observation cycle and circuit breaker."

    def __init__(self, llm: VLLMClient | None = None) -> None:
        self.llm = llm
        self._tools: dict[str, ToolCallable] = {}
        self.graph = self._compile_graph()

    def register(self, name: str, handler: ToolCallable) -> None:
        self._tools[name] = handler

    def _compile_graph(self):
        workflow = StateGraph(ReActState)
        workflow.add_node("agent", self._node_agent)
        workflow.add_node("action", self._node_action)
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent",
            lambda s: "action" if not s.get("final_result") else "finish",
            {"action": "action", "finish": END},
        )
        workflow.add_edge("action", "agent")
        return workflow.compile()

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        if not self.llm or not self._tools:
            return AgentResult(message="ReAct Agent lacks LLM or tools.", degraded=True)
        state: ReActState = {
            "ctx": ctx, "instruction": instruction,
            "messages": [], "iterations": 0, "final_result": None,
        }
        await ctx.emit(f"Starting ReAct Loop: {instruction}", agent_name=self.name)
        final_state = await self.graph.ainvoke(state)
        return final_state.get("final_result") or AgentResult(message="ReAct failed.", degraded=True)

    async def _node_agent(self, state: ReActState) -> ReActState:
        ctx = state["ctx"]
        iters = state.get("iterations", 0)

        # Circuit breaker — prevent dead loops and token bill explosion
        if iters >= MAX_REACT_ITERATIONS:
            await ctx.emit(
                f"ReAct circuit breaker at iteration {iters}. Forcing graceful degradation.",
                agent_name=self.name, event_type="warning",
            )
            return {**state, "final_result": AgentResult(
                message=f"ReAct exceeded max {MAX_REACT_ITERATIONS} iterations.", degraded=True,
            )}

        tool_desc = "\n".join([f"- {name}" for name in self._tools.keys()])
        sys_prompt = REACT_SYSTEM_PROMPT.format(
            tool_descriptions=tool_desc, max_iterations=MAX_REACT_ITERATIONS,
        )
        scratchpad = "\n".join(
            f"{'Assistant' if m['role']=='assistant' else 'Observation'}: {m['content']}"
            for m in state.get("messages", [])
        ) or "(empty — first iteration)"

        user_prompt = (
            f"## GOAL\n{state['instruction']}\n\n"
            f"## SCRATCHPAD\n{scratchpad}\n\n"
            f"## YOUR TURN\nReturn JSON only."
        )
        try:
            result = await self.llm.complete_json(
                [{"role": "system", "content": sys_prompt},
                 {"role": "user", "content": user_prompt}],
                ReActAction, retries=1,
            )
            if not result.ok or not result.data:
                return {**state, "final_result": AgentResult(message="Failed to generate ReAct action.", degraded=True)}

            action: ReActAction = result.data
            await ctx.emit(f"Thought: {action.thought}", agent_name=self.name)

            if action.is_final or not action.action:
                return {**state, "final_result": AgentResult(message=action.final_answer or "Done.")}

            new_msgs = list(state.get("messages", []))
            new_msgs.append({"role": "assistant", "content": f"Thought: {action.thought}\nAction: {action.action}\nAction Input: {action.action_input}"})
            return {**state, "messages": new_msgs, "iterations": iters + 1}
        except Exception as exc:
            return {**state, "final_result": AgentResult(message=f"ReAct reasoning failed: {exc}", degraded=True)}

    async def _node_action(self, state: ReActState) -> ReActState:
        ctx = state["ctx"]
        messages = state.get("messages", [])
        last_msg = messages[-1]["content"] if messages else ""
        action_name, action_input = "", ""
        for line in last_msg.split("\n"):
            if line.startswith("Action:"):
                action_name = line.replace("Action:", "").strip()
            elif line.startswith("Action Input:"):
                action_input = line.replace("Action Input:", "").strip()
        await ctx.emit(f"Executing tool: {action_name}", agent_name=self.name)
        handler = self._tools.get(action_name)
        if not handler:
            obs = f"Error: Tool '{action_name}' not found. Available: {list(self._tools.keys())}"
        else:
            try:
                res = await handler(ctx, action_input)
                obs = res.message
            except Exception as e:
                obs = f"Tool execution failed: {e}"
        new_msgs = list(messages)
        new_msgs.append({"role": "user", "content": f"Observation: {obs}"})
        return {**state, "messages": new_msgs}
