"""Stage 5 Bias-Defended Judge Service (deterministic pre-checks + LLM judge)."""

from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.application.prompts.judge_prompts import (
    JUDGE_SYSTEM_PROMPT,
    build_judge_user_prompt,
)
from app.domain.entities.evaluation import JudgeScore
from app.domain.exceptions import ValidationDomainError
from app.domain.value_objects.enums import FailureCategory

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from app.domain.entities.agent_definition import OutputContract
    from app.domain.entities.document import DocumentChunk
    from app.domain.entities.evaluation import EvalCase
    from app.domain.protocols.llm_gateway import LLMGatewayProtocol

_REFUSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcannot answer\b", re.IGNORECASE),
    re.compile(r"\bcan't answer\b", re.IGNORECASE),
    re.compile(r"\bunable to answer\b", re.IGNORECASE),
    re.compile(r"\bnot covered\b", re.IGNORECASE),
    re.compile(r"\bno information\b", re.IGNORECASE),
    re.compile(r"\bout of scope\b", re.IGNORECASE),
    re.compile(r"\bbeyond the scope\b", re.IGNORECASE),
    re.compile(r"\bnot mentioned\b", re.IGNORECASE),
    re.compile(r"\bnot in the provided\b", re.IGNORECASE),
    re.compile(r"\bdo not have (enough |sufficient )?information\b", re.IGNORECASE),
    re.compile(r"\bcannot provide\b", re.IGNORECASE),
)

_MARKDOWN_STRIP_RE = re.compile(r"[#*_`>]+")
_WHITESPACE_RE = re.compile(r"\s+")
_NUMERIC_TOKEN_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")
_WORD_TOKEN_RE = re.compile(r"[a-z0-9]{4,}", re.IGNORECASE)


def _matches_refusal(response: str, refusal_template: str) -> bool:
    normalized = response.strip().lower()
    if refusal_template and refusal_template.strip().lower() in normalized:
        return True
    return any(pattern.search(response) is not None for pattern in _REFUSAL_PATTERNS)


def _has_citation(response: str, expected_sources: Sequence[str]) -> bool:
    if not expected_sources:
        return True
    lowered = response.lower()
    for src in expected_sources:
        basename = Path(src).name.lower()
        stem = Path(src).stem.lower()
        if basename in lowered or (len(stem) >= 3 and stem in lowered):
            return True
    return False


def _has_fact_anchors(response: str, expected_facts: Sequence[str]) -> bool:
    if not expected_facts:
        return True
    lowered = response.lower()
    for fact in expected_facts:
        numbers = _NUMERIC_TOKEN_RE.findall(fact)
        if numbers:
            if any(num.lower() in lowered for num in numbers):
                return True
            continue
        words = [w.lower() for w in _WORD_TOKEN_RE.findall(fact)]
        if words and any(w in lowered for w in words):
            return True
    return False


def run_deterministic_checks(
    eval_case: EvalCase,
    agent_response: str,
    output_contract: OutputContract,
) -> dict[str, bool]:
    """Stage A deterministic pre-checks (0 LLM calls)."""
    is_refusal = _matches_refusal(agent_response, output_contract.refusal_template)

    if eval_case.should_refuse:
        refusal_match = is_refusal
        citation_present = True
        fact_anchors = True
    else:
        refusal_match = not is_refusal
        citation_present = (
            _has_citation(agent_response, eval_case.expected_sources)
            if output_contract.require_citations
            else True
        )
        fact_anchors = _has_fact_anchors(agent_response, eval_case.expected_facts)

    word_count = len(agent_response.split())
    within_word_limit = word_count <= output_contract.max_response_words

    return {
        "refusal_match": refusal_match,
        "citation_present": citation_present,
        "fact_anchors": fact_anchors,
        "within_word_limit": within_word_limit,
    }


def shuffle_chunks_deterministically(
    chunks: Sequence[DocumentChunk],
    eval_case_id: UUID,
) -> list[DocumentChunk]:
    """Deterministically shuffle retrieved chunks using a SHA-256 seed of eval_case_id."""
    copied = list(chunks)
    digest = hashlib.sha256(str(eval_case_id).encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big")
    rng = random.Random(seed)  # noqa: S311
    rng.shuffle(copied)
    return copied


def normalize_response_for_judge(response: str, max_words: int = 200) -> str:
    """Strip markdown fluff and truncate to a fixed word window to defend against verbosity bias."""
    cleaned = _MARKDOWN_STRIP_RE.sub(" ", response)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    words = cleaned.split()
    if len(words) > max_words:
        return " ".join(words[:max_words])
    return cleaned


def _parse_judge_payload(raw_content: str) -> dict[str, Any]:
    text = raw_content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Judge response JSON must be an object")
    return parsed


def _resolve_failure_category(
    raw_category: str,
    *,
    passed: bool,
    grounded: bool,
    refusal_accurate: bool,
    retrieved_chunks: Sequence[DocumentChunk],
) -> FailureCategory:
    if passed:
        return FailureCategory.NONE
    try:
        cat = FailureCategory(raw_category)
    except ValueError:
        cat = FailureCategory.NONE

    if cat != FailureCategory.NONE:
        return cat
    if not refusal_accurate:
        return FailureCategory.WRONG_REFUSAL
    if not grounded:
        return FailureCategory.HALLUCINATION
    if not retrieved_chunks:
        return FailureCategory.RETRIEVAL_MISS
    return FailureCategory.PROMPT_DEFECT


class JudgeService:
    """Two-stage bias-defended evaluator combining deterministic checks and LLM judging."""

    def __init__(
        self,
        llm_gateway: LLMGatewayProtocol,
        judge_tier: str = "fast-judge",
        agent_model: str = "orchestrator-primary",
        judge_word_window: int = 200,
    ) -> None:
        if judge_tier.strip().lower() == agent_model.strip().lower():
            raise ValidationDomainError(
                code="CROSS_MODEL_VIOLATION",
                detail=(
                    f"Judge tier '{judge_tier}' must be distinct from agent model '{agent_model}'."
                ),
            )
        self._llm = llm_gateway
        self._judge_tier = judge_tier
        self._agent_model = agent_model
        self._judge_word_window = judge_word_window

    async def evaluate_case(
        self,
        *,
        eval_case: EvalCase,
        agent_response: str,
        retrieved_chunks: Sequence[DocumentChunk],
        output_contract: OutputContract,
        latency_ms: int = 0,
    ) -> JudgeScore:
        """Run Stage A deterministic checks and Stage B bias-defended LLM judge."""
        checks = run_deterministic_checks(eval_case, agent_response, output_contract)
        shuffled = shuffle_chunks_deterministically(retrieved_chunks, eval_case.id)
        normalized = normalize_response_for_judge(agent_response, max_words=self._judge_word_window)

        user_prompt = build_judge_user_prompt(
            eval_case=eval_case,
            normalized_response=normalized,
            shuffled_chunks=shuffled,
            deterministic_checks=checks,
        )

        llm_resp = await self._llm.complete(
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            tier=self._judge_tier,
            temperature=0.0,
            max_tokens=512,
            response_format={"type": "json_object"},
        )

        if llm_resp.model.strip().lower() == self._agent_model.strip().lower():
            raise ValidationDomainError(
                code="CROSS_MODEL_VIOLATION",
                detail=(
                    f"Judge model '{llm_resp.model}' matched agent model '{self._agent_model}'."
                ),
            )

        payload = _parse_judge_payload(llm_resp.content)
        grounded = bool(payload.get("grounded", False))
        correct = bool(payload.get("correct", False))
        refusal_accurate = bool(payload.get("refusal_accurate", False))
        reasoning = str(payload.get("reasoning", "")).strip() or "No reasoning provided."

        if eval_case.should_refuse:
            passed = refusal_accurate and checks["refusal_match"] and checks["within_word_limit"]
        else:
            passed = (
                grounded
                and correct
                and refusal_accurate
                and checks["citation_present"]
                and checks["within_word_limit"]
            )

        failure_category = _resolve_failure_category(
            str(payload.get("failure_category", "none")),
            passed=passed,
            grounded=grounded,
            refusal_accurate=refusal_accurate,
            retrieved_chunks=retrieved_chunks,
        )

        return JudgeScore(
            eval_case_id=eval_case.id,
            grounded=grounded,
            correct=correct,
            refusal_accurate=refusal_accurate,
            passed=passed,
            failure_category=failure_category,
            reasoning=reasoning,
            deterministic_checks=checks,
            agent_response=agent_response,
            retrieved_chunk_ids=[c.id for c in retrieved_chunks],
            latency_ms=latency_ms,
        )
