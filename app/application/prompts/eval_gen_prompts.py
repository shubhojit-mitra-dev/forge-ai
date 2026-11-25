"""Committed, versioned prompt templates for Stage 4: Eval Generator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.entities.document import DocumentChunk
    from app.domain.entities.requirements import RequirementsDoc

PROMPT_VERSION = "1.0.0"

EVAL_GENERATOR_SYSTEM_PROMPT = """You are ForgeAI's Principal Evaluation Designer.
Generate realistic, strictly grounded evaluation test cases from the provided document chunks
and RequirementsDoc.

Return ONLY valid JSON matching this exact schema:
{
  "cases": [
    {
      "case_type": "answerable" | "refusal" | "edge",
      "question": "<clear, realistic user question>",
      "expected_sources": ["<exact_filename_from_chunks>"],
      "expected_facts": ["<atomic verifiable fact 1>", "<atomic verifiable fact 2>"],
      "should_refuse": true | false,
      "rationale": "<why this case tests the agent>"
    }
  ]
}

Strict Rules:
1. "answerable": Grounded in the provided chunks; should_refuse=false; expected_sources MUST list
   at least one exact source filename from the chunks; expected_facts MUST contain 2-4 atomic facts.
2. "refusal": Plausible out-of-scope or must_refuse_topics question ABSENT from the documents;
   should_refuse=true; expected_sources=[]; expected_facts=[].
3. "edge": Ambiguous phrasing, multi-document synthesis, boundary conditions, or numeric/table
   lookups; should_refuse=false; expected_sources MUST be non-empty.
4. Do NOT duplicate any existing questions listed in the prompt.
"""


def build_eval_generation_messages(
    requirements: RequirementsDoc,
    chunks: Sequence[DocumentChunk],
    *,
    answerable_target: int,
    refusal_target: int,
    edge_target: int,
    existing_questions: Sequence[str] = (),
) -> list[dict[str, str]]:
    """Build chat messages for Stage 4 batched EvalCase generation."""
    chunk_blocks: list[str] = []
    for chunk in chunks:
        filename = str(chunk.metadata.get("filename", "unknown"))
        chunk_blocks.append(
            f"[Source: {filename} | Chunk #{chunk.chunk_index}]\n{chunk.content.strip()}"
        )

    existing_block = (
        "\n".join(f"- {q}" for q in existing_questions[-25:]) if existing_questions else "- None"
    )

    user_prompt = (
        f"Prompt Version: {PROMPT_VERSION}\n\n"
        f"Agent Name: {requirements.agent_name}\n"
        f"Scope: {requirements.scope}\n"
        f"Must-Answer Topics: {', '.join(requirements.must_answer_topics)}\n"
        f"Must-Refuse Topics: {', '.join(requirements.must_refuse_topics)}\n\n"
        f"Requested Counts for this Batch:\n"
        f"- answerable: {answerable_target}\n"
        f"- refusal: {refusal_target}\n"
        f"- edge: {edge_target}\n\n"
        f"Already Generated Questions (DO NOT REPEAT):\n{existing_block}\n\n"
        f"Document Chunks:\n" + "\n\n".join(chunk_blocks)
    )
    return [
        {"role": "system", "content": EVAL_GENERATOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
