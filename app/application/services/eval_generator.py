"""Stage 4: EvalGeneratorService producing >= 20 grounded EvalCases."""

from __future__ import annotations

import json
import math
import re
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from app.application.prompts.eval_gen_prompts import build_eval_generation_messages
from app.domain.entities.evaluation import EvalCase
from app.domain.exceptions import ValidationDomainError
from app.domain.value_objects.enums import EvalCaseType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.entities.document import DocumentChunk
    from app.domain.entities.requirements import RequirementsDoc
    from app.domain.protocols.llm_gateway import LLMGatewayProtocol

DEFAULT_BATCH_SIZE = 8
MIN_TOTAL_CASES = 20
TARGET_ANSWERABLE = 11
TARGET_REFUSAL = 6
TARGET_EDGE = 5
MAX_TOPUP_ATTEMPTS = 3


def _extract_cases_payload(raw_content: str) -> list[dict[str, Any]]:
    """Extract list of raw eval case dicts from LLM JSON output."""
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict) and isinstance(parsed.get("cases"), list):
        return [item for item in parsed["cases"] if isinstance(item, dict)]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _parse_valid_eval_case(raw: dict[str, Any], project_id: UUID) -> EvalCase | None:
    """Validate a raw LLM eval case dict and return EvalCase or None if invalid."""
    raw_type = raw.get("case_type")
    if not isinstance(raw_type, str):
        return None
    try:
        case_type = EvalCaseType(raw_type.strip().lower())
    except ValueError:
        return None

    question = raw.get("question")
    if not isinstance(question, str) or not question.strip():
        return None

    should_refuse = raw.get("should_refuse")
    if not isinstance(should_refuse, bool):
        return None

    if case_type == EvalCaseType.REFUSAL and not should_refuse:
        return None
    if case_type in (EvalCaseType.ANSWERABLE, EvalCaseType.EDGE) and should_refuse:
        return None

    raw_sources = raw.get("expected_sources", [])
    if not isinstance(raw_sources, list):
        return None
    expected_sources = [str(s).strip() for s in raw_sources if isinstance(s, str) and s.strip()]

    if case_type in (EvalCaseType.ANSWERABLE, EvalCaseType.EDGE) and not expected_sources:
        return None

    raw_facts = raw.get("expected_facts", [])
    expected_facts = (
        [str(f).strip() for f in raw_facts if isinstance(f, str) and f.strip()]
        if isinstance(raw_facts, list)
        else []
    )
    rationale = str(raw.get("rationale", "")).strip() or f"Evaluates {case_type.value} behavior."

    return EvalCase(
        id=uuid4(),
        project_id=project_id,
        case_type=case_type,
        question=question.strip(),
        expected_sources=expected_sources,
        expected_facts=expected_facts,
        should_refuse=should_refuse,
        rationale=rationale,
    )


class EvalGeneratorService:
    """Batches document chunks to generate >= 20 validated EvalCases."""

    def __init__(
        self,
        llm_gateway: LLMGatewayProtocol,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self._llm = llm_gateway
        self._batch_size = batch_size

    async def generate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
        chunks: Sequence[DocumentChunk],
        *,
        min_cases: int = MIN_TOTAL_CASES,
    ) -> list[EvalCase]:
        """Generate at least `min_cases` validated EvalCases across answerable/refusal/edge."""
        if not chunks:
            raise ValidationDomainError(
                code="NO_CHUNKS_FOR_EVAL",
                detail="At least one DocumentChunk is required to generate evaluation cases.",
            )

        batches = [
            chunks[i : i + self._batch_size] for i in range(0, len(chunks), self._batch_size)
        ]
        num_batches = len(batches)
        per_batch_ans = max(1, math.ceil(TARGET_ANSWERABLE / num_batches))
        per_batch_ref = max(1, math.ceil(TARGET_REFUSAL / num_batches))
        per_batch_edge = max(1, math.ceil(TARGET_EDGE / num_batches))

        cases: list[EvalCase] = []
        seen_questions: set[str] = set()

        for batch in batches:
            new_cases = await self._request_batch(
                project_id=project_id,
                requirements=requirements,
                chunks=batch,
                answerable_target=per_batch_ans,
                refusal_target=per_batch_ref,
                edge_target=per_batch_edge,
                existing_questions=[c.question for c in cases],
            )
            self._append_unique(cases, seen_questions, new_cases)

        attempts = 0
        while len(cases) < min_cases and attempts < MAX_TOPUP_ATTEMPTS:
            attempts += 1
            n_ans = sum(1 for c in cases if c.case_type == EvalCaseType.ANSWERABLE)
            n_ref = sum(1 for c in cases if c.case_type == EvalCaseType.REFUSAL)
            n_edge = sum(1 for c in cases if c.case_type == EvalCaseType.EDGE)

            deficit = min_cases - len(cases)
            ans_need = max(0, TARGET_ANSWERABLE - n_ans)
            ref_need = max(0, TARGET_REFUSAL - n_ref)
            edge_need = max(0, TARGET_EDGE - n_edge)
            if ans_need + ref_need + edge_need == 0:
                ans_need = deficit

            topup_chunks = chunks[: self._batch_size]
            new_cases = await self._request_batch(
                project_id=project_id,
                requirements=requirements,
                chunks=topup_chunks,
                answerable_target=ans_need,
                refusal_target=ref_need,
                edge_target=edge_need,
                existing_questions=[c.question for c in cases],
            )
            self._append_unique(cases, seen_questions, new_cases)

        if len(cases) < min_cases:
            raise ValidationDomainError(
                code="INSUFFICIENT_EVAL_CASES",
                detail=(
                    f"Generated only {len(cases)} valid EvalCases; "
                    f"at least {min_cases} are required."
                ),
            )

        return cases

    async def _request_batch(
        self,
        *,
        project_id: UUID,
        requirements: RequirementsDoc,
        chunks: Sequence[DocumentChunk],
        answerable_target: int,
        refusal_target: int,
        edge_target: int,
        existing_questions: Sequence[str],
    ) -> list[EvalCase]:
        messages = build_eval_generation_messages(
            requirements=requirements,
            chunks=chunks,
            answerable_target=answerable_target,
            refusal_target=refusal_target,
            edge_target=edge_target,
            existing_questions=existing_questions,
        )
        response = await self._llm.complete(
            messages=messages,
            tier="orchestrator-primary",
            temperature=0.2,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        raw_items = _extract_cases_payload(response.content)
        parsed: list[EvalCase] = []
        for item in raw_items:
            case = _parse_valid_eval_case(item, project_id)
            if case is not None:
                parsed.append(case)
        return parsed

    @staticmethod
    def _append_unique(
        cases: list[EvalCase],
        seen_questions: set[str],
        candidates: Sequence[EvalCase],
    ) -> None:
        for candidate in candidates:
            key = candidate.question.lower()
            if key not in seen_questions:
                seen_questions.add(key)
                cases.append(candidate)
