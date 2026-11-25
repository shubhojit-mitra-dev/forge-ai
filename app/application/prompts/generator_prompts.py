"""Committed, versioned prompt templates for Stage 3: Agent Generator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.entities.requirements import RequirementsDoc

PROMPT_VERSION = "1.0.0"

AGENT_GENERATOR_SYSTEM_PROMPT = """You are ForgeAI's Principal Agent Architect.
Your task is to design a production-grade AI agent specification from a validated RequirementsDoc,
document summaries, and available tool descriptions.

Return ONLY valid JSON matching this exact schema:
{
  "system_prompt": "<detailed, grounded system prompt >= 50 chars>",
  "retrieval_config": {
    "chunk_size": 600,
    "chunk_overlap": 100,
    "top_k": 5,
    "similarity_threshold": 0.35,
    "hybrid_search": true
  },
  "selected_tools": ["<tool_name>"],
  "output_contract": {
    "format": "markdown",
    "require_citations": true,
    "refusal_template": "<clear out-of-scope refusal message>",
    "max_response_words": 350
  }
}

Strict Rules:
1. Grounding: The system_prompt MUST instruct the agent to answer ONLY from retrieved document
   context and tool outputs, cite source filenames, and refuse out-of-scope topics using the
   refusal_template.
2. Strict Tool Discipline: Attach ONLY tools that are genuinely required by the brief and
   detected_tool_needs. NEVER attach irrelevant tools (e.g., weather_http for HR, legal, finance,
   or procurement briefs; csv_lookup when no tabular/CSV catalog is involved).
3. Parameter bounds: chunk_size in [200, 2000], chunk_overlap in [0, 400] (< chunk_size),
   top_k in [1, 15], similarity_threshold in [0.0, 1.0], max_response_words in [50, 1000].
"""


def build_agent_generator_messages(
    requirements: RequirementsDoc,
    doc_summaries: Sequence[str],
    tool_descriptions: Sequence[tuple[str, str]],
) -> list[dict[str, str]]:
    """Build chat messages for Stage 3 AgentDefinition generation."""
    qa_lines = (
        "\n".join(f"- Q: {qa.question}\n  A: {qa.answer}" for qa in requirements.clarifying_qa)
        or "- None"
    )
    summary_lines = "\n".join(f"- {summary}" for summary in doc_summaries) or "- None"
    tool_lines = (
        "\n".join(f"- {name}: {desc}" for name, desc in tool_descriptions) or "- None available"
    )
    detected_tools = ", ".join(tool.value for tool in requirements.detected_tool_needs) or "none"

    user_prompt = (
        f"Prompt Version: {PROMPT_VERSION}\n\n"
        f"Agent Name: {requirements.agent_name}\n"
        f"Scope: {requirements.scope}\n"
        f"Target Audience: {requirements.target_audience}\n"
        f"Tone: {requirements.tone}\n"
        f"Must-Answer Topics: {', '.join(requirements.must_answer_topics)}\n"
        f"Must-Refuse Topics: {', '.join(requirements.must_refuse_topics)}\n"
        f"Detected Tool Needs: {detected_tools}\n\n"
        f"Clarifying Q&A:\n{qa_lines}\n\n"
        f"Document Summaries:\n{summary_lines}\n\n"
        f"Available Tools:\n{tool_lines}\n\n"
        "Generate the AgentDefinition JSON now."
    )
    return [
        {"role": "system", "content": AGENT_GENERATOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
