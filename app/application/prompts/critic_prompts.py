"""Versioned prompt templates for the Stage 6 Critic-Optimizer targeted patcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.entities.agent_definition import AgentDefinition
    from app.domain.entities.evaluation import JudgeScore
    from app.domain.value_objects.enums import FailureCategory

CRITIC_PATCH_SYSTEM_PROMPT = """You are the ForgeAI Critic-Optimizer.
Your job is to apply a SURGICAL, TARGETED PATCH to fix the dominant failure pattern in an AI agent.
Do NOT regenerate the entire agent or change unrelated instructions or tools.

Rules:
1. Preserve the agent's core persona, scope, and valid existing rules.
2. Only add or refine the minimal instruction(s) or output contract field(s) needed to fix the
   dominant failure category.
3. Output ONLY valid JSON matching this schema:
{
  "what_changed": <string: concise summary of the targeted edit>,
  "why": <string: why this edit addresses the dominant failure category>,
  "patched_system_prompt": <string or null>,
  "patched_refusal_template": <string or null>,
  "patched_require_citations": <boolean or null>,
  "patched_max_response_words": <integer or null>
}
"""


def build_critic_patch_prompt(
    *,
    agent: AgentDefinition,
    dominant_category: FailureCategory,
    failing_scores: Sequence[JudgeScore],
) -> str:
    """Build the user prompt describing the dominant failure pattern for surgical patching."""
    failures_summary = "\n".join(
        f"- case={s.eval_case_id} | category={s.failure_category.value} | "
        f"checks={s.deterministic_checks} | reason={s.reasoning}"
        for s in failing_scores[:6]
    )

    return (
        f"Dominant Failure Category: {dominant_category.value}\n\n"
        f"Current System Prompt:\n{agent.system_prompt}\n\n"
        f"Current Output Contract:\n"
        f"- format: {agent.output_contract.format}\n"
        f"- require_citations: {agent.output_contract.require_citations}\n"
        f"- refusal_template: {agent.output_contract.refusal_template}\n"
        f"- max_response_words: {agent.output_contract.max_response_words}\n\n"
        f"Sample Failing Evaluations:\n{failures_summary}\n"
    )
