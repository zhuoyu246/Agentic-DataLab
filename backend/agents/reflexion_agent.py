"""
ReflexionAgent — LLM-Powered Self-Correction Critic with Circuit Breaker.

Architecture (Reflection Paradigm):
Implements the Generator → Environment → Critic feedback loop where
the LLM analyzes failures and generates constructive revision guidance.

Academic reference: "Reflexion: Language Agents with Verbal Reinforcement Learning"
                    (Shinn et al., 2023)

Key features:
- Production-grade Reflection prompt that analyzes WHY a step failed
- Generates actionable, specific feedback (not generic retry instructions)
- Hard circuit breaker (max_reflection_depth = 3) prevents infinite retry loops
- Only provides guidance — does NOT write code itself (separation of concerns)
"""
from __future__ import annotations

from agents.base import AgentContext, AgentResult, BaseAgent
from core.llm import VLLMClient

# ---------------------------------------------------------------------------
# Production-Grade Reflection System Prompt
# ---------------------------------------------------------------------------
REFLECTION_SYSTEM_PROMPT = """\
You are an expert reviewer, code critic, and debugging specialist.

## ROLE
You are given a PREVIOUS ATTEMPT at a task that FAILED. Your job is to:
1. Carefully analyze the failure and explain exactly WHY it happened
2. Identify the ROOT CAUSE (not just the symptom)
3. Provide ACTIONABLE, SPECIFIC feedback on how to fix it
4. Suggest a revised instruction that avoids the same mistake

## CRITICAL RULES
- Do NOT write the actual code yourself. Only provide the detailed reflection.
- Be SPECIFIC: instead of "try a different approach", say exactly what to change.
- If the error is a data issue (missing column, wrong type), suggest data preparation steps.
- If the error is a logic issue, explain the correct logic.
- If the error is an environment issue (missing package, connection timeout),
  suggest deterministic fallback strategies.
- Keep your reflection concise but thorough (max 500 words).
- End with a clear, revised one-sentence instruction for the retry attempt.

## OUTPUT FORMAT
Structure your response as:
1. **Failure Analysis**: What went wrong and why
2. **Root Cause**: The underlying issue
3. **Recommended Fix**: Specific steps to resolve
4. **Revised Instruction**: A single clear sentence for the retry
"""


class ReflexionAgent(BaseAgent):
    """
    Self-healing step rewriter with LLM-powered critique.

    When a specialist agent fails, the Reflexion agent:
    1. Receives the error message and original instruction
    2. Uses LLM to analyze the failure root cause
    3. Generates a constructive revised instruction
    4. Returns the revised instruction for the supervisor to retry

    The circuit breaker (max_reflexion in SupervisorState) prevents
    this from becoming an infinite retry loop. Typically set to 3.
    """
    name = "reflexion_agent"
    description = "Self-healing step rewriter with LLM-powered critique and hard Max-Steps circuit breaker."

    def __init__(self, llm: VLLMClient | None = None) -> None:
        self.llm = llm

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        """
        Analyze a failure and generate a revised instruction.

        Args:
            ctx: Agent execution context
            instruction: The error message or failure description to analyze

        Returns:
            AgentResult with a revised instruction in the message field
        """
        await ctx.emit(
            "Reflexion critic analyzing failure...",
            agent_name=self.name,
        )

        # Try LLM-powered reflection first
        if self.llm is not None and await self.llm.is_available():
            try:
                user_prompt = (
                    f"## FAILED STEP DETAILS\n"
                    f"Error/Failure: {instruction[:2000]}\n\n"
                    f"## CONTEXT\n"
                    f"Session: {ctx.session_id}\n"
                    f"Active Dataset: {ctx.active_dataset_id or 'None'}\n\n"
                    f"Please analyze this failure and provide your reflection."
                )

                response = await self.llm.complete(
                    [
                        {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,  # Low temperature for analytical precision
                    max_tokens=800,
                )

                await ctx.emit(
                    f"Reflexion generated LLM-powered revision guidance.",
                    agent_name=self.name,
                )

                return AgentResult(
                    message=response.strip(),
                    metrics={"reflection_type": "llm_powered", "retryable": True},
                )

            except Exception as exc:
                await ctx.emit(
                    f"LLM reflection degraded to heuristic: {exc}",
                    agent_name=self.name,
                    event_type="warning",
                )

        # Heuristic fallback when LLM is unavailable
        safe_instruction = (
            "Retry with a narrower deterministic action. "
            "Avoid repeating failed tool calls. "
            "If the error involves missing data, check if a data_loader "
            "or cleaning step is needed first. "
            f"Original failure: {instruction[:1000]}"
        )
        await ctx.emit(
            "Reflexion generated heuristic retry instruction.",
            agent_name=self.name,
        )
        return AgentResult(
            message=safe_instruction,
            metrics={"reflection_type": "heuristic_fallback", "retryable": True},
        )
