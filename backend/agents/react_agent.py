from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from agents.base import AgentContext, AgentResult, BaseAgent
from core.llm import VLLMClient

ToolCallable = Callable[[AgentContext, str], Awaitable[AgentResult]]


class ReActAction(BaseModel):
    thought: str = Field(description="Your reasoning for the next step.")
    action: str | None = Field(description="Name of the tool to use. Null if is_final is True.")
    action_input: str | None = Field(description="Input string for the tool.")
    is_final: bool = Field(description="Set to true if goal is achieved or no tool fits.")
    final_answer: str | None = Field(description="The final summary or answer.")


class ReActState(TypedDict, total=False):
    ctx: AgentContext
    instruction: str
    messages: list[dict[str, str]]
    iterations: int
    final_result: AgentResult | None


class ReActToolAgent(BaseAgent):
    name = "react_tool_agent"
    description = "LangGraph-powered ReAct loop for tool calling."

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
            "ctx": ctx,
            "instruction": instruction,
            "messages": [],
            "iterations": 0,
            "final_result": None,
        }
        
        await ctx.emit(f"Starting ReAct Loop for instruction: {instruction}", agent_name=self.name)
        final_state = await self.graph.ainvoke(state)
        return final_state.get("final_result") or AgentResult(message="ReAct failed.", degraded=True)

    async def _node_agent(self, state: ReActState) -> ReActState:
        ctx = state["ctx"]
        iters = state.get("iterations", 0)
        
        if iters >= 5:
            await ctx.emit("ReAct loop exceeded maximum iterations.", agent_name=self.name, event_type="warning")
            return {**state, "final_result": AgentResult(message="Too many iterations.", degraded=True)}

        tool_desc = "\n".join([f"- {name}" for name in self._tools.keys()])
        sys_prompt = (
            "You are a ReAct-based AI assistant.\n"
            f"Available tools:\n{tool_desc}\n\n"
            "If none of the tools match the user's instruction, set is_final to true immediately.\n"
            "Return JSON matching the schema."
        )

        history = "\n".join([f"{m['role']}: {m['content']}" for m in state.get("messages", [])])
        user_prompt = f"Goal: {state['instruction']}\n\nScratchpad:\n{history}\n\nWhat is your next action?"

        try:
            result = await self.llm.complete_json(
                [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                ReActAction,
                retries=1
            )
            if not result.ok or not result.data:
                return {**state, "final_result": AgentResult(message="Failed to generate JSON action.", degraded=True)}
            
            action: ReActAction = result.data
            await ctx.emit(f"Thought: {action.thought}", agent_name=self.name)
            
            if action.is_final or not action.action:
                return {**state, "final_result": AgentResult(message=action.final_answer or "Done.")}
                
            new_msgs = list(state.get("messages", []))
            new_msgs.append({"role": "assistant", "content": f"Action: {action.action}\nInput: {action.action_input}"})
            return {**state, "messages": new_msgs, "iterations": iters + 1}
            
        except Exception as exc:
            return {**state, "final_result": AgentResult(message=str(exc), degraded=True)}

    async def _node_action(self, state: ReActState) -> ReActState:
        ctx = state["ctx"]
        messages = state.get("messages", [])
        last_msg = messages[-1]["content"] if messages else ""
        
        action_name = ""
        action_input = ""
        for line in last_msg.split('\n'):
            if line.startswith("Action:"):
                action_name = line.replace("Action:", "").strip()
            elif line.startswith("Input:"):
                action_input = line.replace("Input:", "").strip()
                
        await ctx.emit(f"Executing tool: {action_name}", agent_name=self.name)
        handler = self._tools.get(action_name)
        if not handler:
            obs = f"Error: Tool {action_name} not found."
        else:
            try:
                res = await handler(ctx, action_input)
                obs = res.message
            except Exception as e:
                obs = f"Tool execution failed: {e}"
                
        new_msgs = list(messages)
        new_msgs.append({"role": "user", "content": f"Observation: {obs}"})
        return {**state, "messages": new_msgs}

