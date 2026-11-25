"""Versioned prompt templates for Stage 1 (Intake Interviewer)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.entities.requirements import ClarifyingQA

PROMPT_VERSION = "1.0.0"

INTAKE_QUESTIONS_SYSTEM_PROMPT = """You are the ForgeAI Intake Interviewer (Stage 1).
Your goal is to ask AT MOST 5 concise, high-impact clarifying questions to resolve ambiguities
in the user's agent brief relative to their uploaded document summaries.

Rules:
1. Return ONLY valid JSON matching: {"questions": ["question 1", ...]}.
2. Never generate more than 5 questions. Fewer is better if the brief is already clear.
3. Focus on: target audience, tone/format, must-answer vs must-refuse boundaries, and tool needs.
4. Do NOT ask questions already answered in the brief or document summaries.
"""

INTAKE_FINALIZE_SYSTEM_PROMPT = """You are the ForgeAI Requirements Synthesizer (Stage 1).
Synthesize the user's brief, uploaded document summaries, and clarifying Q&A into a strict
RequirementsDoc JSON object.

Rules:
1. Return ONLY valid JSON with exact keys:
   - "agent_name": string (3-80 chars, descriptive)
   - "scope": string (min 10 chars, clear boundary of what the agent does)
   - "target_audience": string (min 3 chars)
   - "tone": string (min 3 chars)
   - "must_answer_topics": non-empty list of strings (core topics grounded in the docs)
   - "must_refuse_topics": non-empty list of strings (out-of-scope topics the agent MUST refuse)
   - "detected_tool_needs": list of tool names from ONLY:
     ["csv_lookup", "calculator", "weather_http", "current_date"]
2. Tool discipline: ONLY include a tool in "detected_tool_needs" if the brief or docs
   explicitly require it (e.g., CSV lookup, math calculations, live weather, or current date).
   Do NOT attach unnecessary tools.
"""


def build_intake_questions_messages(
    brief: str,
    doc_summaries: list[str],
) -> list[dict[str, str]]:
    """Build chat messages for generating up to 5 intake clarifying questions."""
    docs_block = "\n".join(f"- {summary}" for summary in doc_summaries) or "(No documents provided)"
    user_content = (
        f"Agent Brief:\n{brief.strip()}\n\n"
        f"Uploaded Document Summaries:\n{docs_block}\n\n"
        "Generate up to 5 clarifying questions as JSON."
    )
    return [
        {"role": "system", "content": INTAKE_QUESTIONS_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_intake_finalize_messages(
    brief: str,
    doc_summaries: list[str],
    qa_pairs: list[ClarifyingQA],
) -> list[dict[str, str]]:
    """Build chat messages for synthesizing a structured RequirementsDoc."""
    docs_block = "\n".join(f"- {summary}" for summary in doc_summaries) or "(No documents provided)"
    qa_block = (
        "\n".join(f"Q: {qa.question}\nA: {qa.answer}" for qa in qa_pairs)
        or "(No clarifying Q&A provided)"
    )
    user_content = (
        f"Agent Brief:\n{brief.strip()}\n\n"
        f"Uploaded Document Summaries:\n{docs_block}\n\n"
        f"Clarifying Q&A:\n{qa_block}\n\n"
        "Produce the RequirementsDoc JSON."
    )
    return [
        {"role": "system", "content": INTAKE_FINALIZE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
