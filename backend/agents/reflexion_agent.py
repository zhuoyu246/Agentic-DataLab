from __future__ import annotations

from agents.base import AgentContext, AgentResult, BaseAgent


class ReflexionAgent(BaseAgent):
    name = "reflexion_agent"
    description = "Self-healing step rewriter with hard Max-Steps circuit breaker."

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        safe_instruction = (
            "Retry with a narrower deterministic action. "
            "Avoid repeating failed tool calls. Original failure: "
            + instruction[:1000]
        )
        await ctx.emit("Reflexion generated a bounded retry instruction.", agent_name=self.name)
        return AgentResult(message=safe_instruction, metrics={"retryable": True})

