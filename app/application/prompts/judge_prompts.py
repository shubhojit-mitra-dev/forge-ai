"""Versioned prompt templates for the Stage 5 Bias-Defended LLM Judge."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.entities.document import DocumentChunk
    from app.domain.entities.evaluation import EvalCase

JUDGE_SYSTEM_PROMPT = """You are an impartial, strict evaluation judge for ForgeAI.
Your task is to evaluate an AI agent's response against retrieved source chunks and ground-truth
expectations.

CRITICAL SCORING RULES (Bias Defenses):
1. Score strictly on factual alignment with `expected_facts` and `retrieved_context`.
2. Longer or more verbose answers do NOT earn higher points; concise, accurate answers score
   equally well.
3. Ignore formatting style or persuasive tone; verify only whether claims are grounded in the
   provided chunks.
4. If `should_refuse` is true, the agent MUST refuse without fabricating facts.
5. Output ONLY valid JSON matching this exact schema:
{
  "grounded": <boolean>,
  "correct": <boolean>,
  "refusal_accurate": <boolean>,
  "failure_category": <"none"|"retrieval_miss"|"prompt_defect"|"hallucination"|"wrong_refusal">,
  "reasoning": <string: concise 1-2 sentence explanation>
}
"""


def build_judge_user_prompt(
    *,
    eval_case: EvalCase,
    normalized_response: str,
    shuffled_chunks: Sequence[DocumentChunk],
    deterministic_checks: dict[str, bool],
) -> str:
    """Build the structured user prompt for Stage B LLM judging."""
    chunks_block = "\n\n".join(
        f"[Chunk {idx + 1} | source={chunk.metadata.get('filename', 'unknown')}]\n{chunk.content}"
        for idx, chunk in enumerate(shuffled_chunks)
    )
    if not chunks_block:
        chunks_block = "(No chunks retrieved)"

    facts_block = "\n".join(f"- {fact}" for fact in eval_case.expected_facts) or "- (None)"
    sources_block = ", ".join(eval_case.expected_sources) or "(None)"
    checks_block = ", ".join(f"{k}={v}" for k, v in deterministic_checks.items())

    return (
        f"Question: {eval_case.question}\n"
        f"Case Type: {eval_case.case_type.value}\n"
        f"Should Refuse: {eval_case.should_refuse}\n"
        f"Expected Sources: {sources_block}\n"
        f"Expected Facts:\n{facts_block}\n\n"
        f"Deterministic Pre-Checks: {checks_block}\n\n"
        f"Normalized Agent Response:\n{normalized_response}\n\n"
        f"Retrieved Context (shuffled order):\n{chunks_block}\n"
    )
