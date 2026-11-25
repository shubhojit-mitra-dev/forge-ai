"""Versioned prompt templates for Stage 2 (Groundability Guard)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.entities.document import DocumentChunk

PROMPT_VERSION = "1.0.0"

GROUNDABILITY_SYSTEM_PROMPT = """You are the ForgeAI Groundability Guard (Stage 2).
Your job is to verify whether the retrieved document chunks contain sufficient factual
evidence to answer the required topic without hallucination.

Rules:
1. Return ONLY valid JSON with exact keys:
   - "is_grounded": boolean (true ONLY if the chunks provide concrete evidence for the topic)
   - "confidence": float between 0.0 and 1.0
   - "supporting_documents": list of source filenames from the chunks that support the topic
   - "gap_reason": string explaining what is missing if is_grounded is false or confidence < 0.45,
     otherwise null
2. Be strict and honest: if the chunks only tangentially mention keywords without answering
   the topic, set "is_grounded": false and confidence < 0.45.
"""


def build_groundability_messages(
    topic: str,
    chunks: list[DocumentChunk],
) -> list[dict[str, str]]:
    """Build chat messages to assess groundability of a single must-answer topic."""
    chunk_blocks: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        filename = str(chunk.metadata.get("filename", "unknown"))
        chunk_blocks.append(f"[Chunk {idx} | source={filename}]\n{chunk.content}")

    chunks_text = "\n\n".join(chunk_blocks) if chunk_blocks else "(No chunks retrieved)"
    user_content = (
        f"Required Topic:\n{topic.strip()}\n\n"
        f"Retrieved Document Chunks:\n{chunks_text}\n\n"
        "Assess groundability as JSON."
    )
    return [
        {"role": "system", "content": GROUNDABILITY_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
