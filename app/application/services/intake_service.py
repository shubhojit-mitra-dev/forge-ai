"""Stage 1 Intake Interviewer service: clarifying questions and RequirementsDoc."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from app.application.prompts.intake_prompts import (
    build_intake_finalize_messages,
    build_intake_questions_messages,
)
from app.domain.entities.requirements import ClarifyingQA, RequirementsDoc
from app.domain.exceptions import ValidationDomainError
from app.domain.value_objects.enums import ToolName

if TYPE_CHECKING:
    from app.domain.protocols.llm_gateway import LLMGatewayProtocol

MAX_CLARIFYING_QUESTIONS = 5


def _parse_json_payload(raw_content: str) -> dict[str, Any]:
    """Strip optional markdown code fences and decode a JSON object."""
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValidationDomainError(
            "INVALID_LLM_JSON",
            f"LLM returned invalid JSON: {exc}",
        ) from exc

    if not isinstance(parsed, dict):
        raise ValidationDomainError(
            "INVALID_LLM_JSON",
            "Expected a JSON object from LLM response.",
        )
    return parsed


class IntakeService:
    """Handles Stage 1 clarifying question generation and requirements synthesis."""

    def __init__(
        self,
        llm_gateway: LLMGatewayProtocol,
        tier: str = "orchestrator-primary",
    ) -> None:
        self._llm_gateway = llm_gateway
        self._tier = tier

    async def generate_questions(
        self,
        brief: str,
        doc_summaries: list[str],
    ) -> list[str]:
        """Generate up to 5 clarifying questions from the user brief and doc summaries."""
        if not brief.strip():
            raise ValidationDomainError("EMPTY_BRIEF", "Project brief cannot be empty.")

        messages = build_intake_questions_messages(brief=brief, doc_summaries=doc_summaries)
        response = await self._llm_gateway.complete(
            messages=messages,
            tier=self._tier,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        payload = _parse_json_payload(response.content)
        raw_questions = payload.get("questions", [])
        if not isinstance(raw_questions, list):
            raise ValidationDomainError(
                "INVALID_LLM_JSON",
                "Expected 'questions' to be a list of strings.",
            )

        questions = [str(q).strip() for q in raw_questions if str(q).strip()]
        return questions[:MAX_CLARIFYING_QUESTIONS]

    async def finalize_requirements(
        self,
        brief: str,
        doc_summaries: list[str],
        qa_pairs: list[ClarifyingQA],
    ) -> RequirementsDoc:
        """Synthesize brief, doc summaries, and Q&A pairs into a RequirementsDoc."""
        if not brief.strip():
            raise ValidationDomainError("EMPTY_BRIEF", "Project brief cannot be empty.")
        if len(qa_pairs) > MAX_CLARIFYING_QUESTIONS:
            raise ValidationDomainError(
                "TOO_MANY_CLARIFYING_QUESTIONS",
                f"clarifying_qa cannot exceed {MAX_CLARIFYING_QUESTIONS} items.",
            )

        messages = build_intake_finalize_messages(
            brief=brief,
            doc_summaries=doc_summaries,
            qa_pairs=qa_pairs,
        )
        response = await self._llm_gateway.complete(
            messages=messages,
            tier=self._tier,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        payload = _parse_json_payload(response.content)

        raw_tools = payload.get("detected_tool_needs", [])
        if not isinstance(raw_tools, list):
            raw_tools = []
        valid_tools: list[ToolName] = []
        for item in raw_tools:
            try:
                valid_tools.append(ToolName(str(item)))
            except ValueError:
                continue

        must_answer = [
            str(t).strip() for t in payload.get("must_answer_topics", []) if str(t).strip()
        ]
        must_refuse = [
            str(t).strip() for t in payload.get("must_refuse_topics", []) if str(t).strip()
        ]
        if not must_answer or not must_refuse:
            raise ValidationDomainError(
                "INVALID_REQUIREMENTS",
                "RequirementsDoc must include at least one must_answer and must_refuse topic.",
            )

        return RequirementsDoc(
            agent_name=str(payload.get("agent_name", "")).strip(),
            scope=str(payload.get("scope", "")).strip(),
            target_audience=str(payload.get("target_audience", "")).strip(),
            tone=str(payload.get("tone", "")).strip(),
            must_answer_topics=must_answer,
            must_refuse_topics=must_refuse,
            clarifying_qa=list(qa_pairs),
            detected_tool_needs=valid_tools,
        )
