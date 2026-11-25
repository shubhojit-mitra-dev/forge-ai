"""Stage 6 Critic-Optimizer Service (failure classification & targeted patching)."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from app.application.prompts.critic_prompts import (
    CRITIC_PATCH_SYSTEM_PROMPT,
    build_critic_patch_prompt,
)
from app.domain.entities.agent_definition import (
    AgentDefinition,
    OutputContract,
    RetrievalConfig,
)
from app.domain.entities.evaluation import IterationLog, JudgeScore
from app.domain.value_objects.enums import FailureCategory

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence
    from uuid import UUID

    from app.domain.protocols.llm_gateway import LLMGatewayProtocol


@dataclass(slots=True, frozen=True)
class OptimizationResult:
    """Outcome of the bounded Critic-Optimizer loop."""

    final_agent: AgentDefinition
    final_scores: list[JudgeScore]
    iteration_logs: list[IterationLog]
    stop_reason: str


def _compute_pass_rate(scores: Sequence[JudgeScore]) -> float:
    if not scores:
        return 0.0
    passed = sum(1 for s in scores if s.passed)
    return passed / len(scores)


def _classify_dominant_failure(
    scores: Sequence[JudgeScore],
) -> tuple[FailureCategory, list[JudgeScore]]:
    failing = [s for s in scores if not s.passed]
    if not failing:
        return FailureCategory.NONE, []
    counts = Counter(
        s.failure_category
        if s.failure_category != FailureCategory.NONE
        else FailureCategory.PROMPT_DEFECT
        for s in failing
    )
    dominant, _ = counts.most_common(1)[0]
    targeted = [s for s in failing if s.failure_category == dominant] or failing
    return dominant, targeted


def _patch_retrieval_config(current: RetrievalConfig) -> tuple[RetrievalConfig, str, str]:
    new_top_k = min(15, current.top_k + 3)
    new_threshold = max(0.15, round(current.similarity_threshold - 0.08, 2))
    new_config = RetrievalConfig(
        chunk_size=current.chunk_size,
        chunk_overlap=current.chunk_overlap,
        top_k=new_top_k,
        similarity_threshold=new_threshold,
        hybrid_search=True,
    )
    what_changed = (
        f"Adjusted RetrievalConfig: top_k {current.top_k}->{new_top_k}, "
        f"similarity_threshold {current.similarity_threshold}->{new_threshold}, hybrid_search=True."
    )
    why = (
        "Dominant retrieval_miss failures indicate relevant chunks were missed at current "
        "k/threshold."
    )
    return new_config, what_changed, why


def _parse_patch_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Critic patch JSON must be an object")
    return parsed


class CriticOptimizerService:
    """Bounded Critic-Optimizer applying targeted patches without full agent regeneration."""

    def __init__(
        self,
        llm_gateway: LLMGatewayProtocol,
        critic_tier: str = "orchestrator-primary",
        max_iterations: int = 3,
        target_pass_rate: float = 0.90,
        min_delta: float = 0.02,
        min_call_budget: int = 25,
    ) -> None:
        self._llm = llm_gateway
        self._critic_tier = critic_tier
        self._max_iterations = max_iterations
        self._target_pass_rate = target_pass_rate
        self._min_delta = min_delta
        self._min_call_budget = min_call_budget

    async def optimize(
        self,
        *,
        agent: AgentDefinition,
        evaluate_fn: Callable[[AgentDefinition], Awaitable[list[JudgeScore]]],
        remaining_call_budget: int = 120,
        on_iteration: Callable[[IterationLog], Awaitable[None]] | None = None,
    ) -> OptimizationResult:
        """Run up to `max_iterations` targeted improvement cycles with early stopping."""
        current_agent = agent
        current_scores = await evaluate_fn(current_agent)
        current_pass_rate = _compute_pass_rate(current_scores)
        iteration_logs: list[IterationLog] = []
        stop_reason = "max_iterations_reached"

        if current_pass_rate >= self._target_pass_rate:
            return OptimizationResult(
                final_agent=current_agent,
                final_scores=current_scores,
                iteration_logs=iteration_logs,
                stop_reason="target_pass_rate_reached",
            )

        for iteration in range(1, self._max_iterations + 1):
            if remaining_call_budget < self._min_call_budget:
                stop_reason = "budget_cap_reached"
                break

            dominant_category, targeted_failures = _classify_dominant_failure(current_scores)
            if dominant_category == FailureCategory.NONE:
                stop_reason = "target_pass_rate_reached"
                break

            patched_agent, change_type, what_changed, why = await self._apply_targeted_patch(
                agent=current_agent,
                dominant_category=dominant_category,
                failing_scores=targeted_failures,
            )
            if change_type != "retrieval_config":
                remaining_call_budget -= 1

            next_scores = await evaluate_fn(patched_agent)
            remaining_call_budget -= len(next_scores)
            next_pass_rate = _compute_pass_rate(next_scores)

            failures_addressed: list[UUID] = [s.eval_case_id for s in targeted_failures]
            log = IterationLog(
                iteration=iteration,
                score_before=current_pass_rate,
                score_after=next_pass_rate,
                failures_addressed=failures_addressed,
                change_type=change_type,
                what_changed=what_changed,
                why=why,
            )
            iteration_logs.append(log)
            if on_iteration is not None:
                await on_iteration(log)

            delta = next_pass_rate - current_pass_rate
            current_agent = patched_agent
            current_scores = next_scores
            current_pass_rate = next_pass_rate

            if current_pass_rate >= self._target_pass_rate:
                stop_reason = "target_pass_rate_reached"
                break
            if delta < self._min_delta:
                stop_reason = "diminishing_returns"
                break
        else:
            stop_reason = "max_iterations_reached"

        return OptimizationResult(
            final_agent=current_agent,
            final_scores=current_scores,
            iteration_logs=iteration_logs,
            stop_reason=stop_reason,
        )

    async def _apply_targeted_patch(
        self,
        *,
        agent: AgentDefinition,
        dominant_category: FailureCategory,
        failing_scores: Sequence[JudgeScore],
    ) -> tuple[
        AgentDefinition,
        Literal["retrieval_config", "system_prompt", "output_contract", "tool_selection"],
        str,
        str,
    ]:
        if dominant_category == FailureCategory.RETRIEVAL_MISS:
            new_retrieval, what_changed, why = _patch_retrieval_config(agent.retrieval_config)
            return (
                agent.bump_version(retrieval_config=new_retrieval),
                "retrieval_config",
                what_changed,
                why,
            )

        user_prompt = build_critic_patch_prompt(
            agent=agent,
            dominant_category=dominant_category,
            failing_scores=failing_scores,
        )
        response = await self._llm.complete(
            messages=[
                {"role": "system", "content": CRITIC_PATCH_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            tier=self._critic_tier,
            temperature=0.0,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        patch = _parse_patch_json(response.content)
        what_changed = str(patch.get("what_changed") or f"Patched for {dominant_category.value}")
        why = str(patch.get("why") or f"Address {dominant_category.value} failures.")

        patched_prompt = patch.get("patched_system_prompt")
        patched_refusal = patch.get("patched_refusal_template")
        patched_citations = patch.get("patched_require_citations")
        patched_max_words = patch.get("patched_max_response_words")

        if isinstance(patched_prompt, str) and len(patched_prompt.strip()) >= 50:
            return (
                agent.bump_version(system_prompt=patched_prompt.strip()),
                "system_prompt",
                what_changed,
                why,
            )

        new_contract = OutputContract(
            format=agent.output_contract.format,
            require_citations=(
                bool(patched_citations)
                if patched_citations is not None
                else agent.output_contract.require_citations
            ),
            refusal_template=(
                str(patched_refusal).strip()
                if isinstance(patched_refusal, str) and patched_refusal.strip()
                else agent.output_contract.refusal_template
            ),
            max_response_words=(
                int(patched_max_words)
                if isinstance(patched_max_words, int) and 50 <= patched_max_words <= 1000
                else agent.output_contract.max_response_words
            ),
        )
        return (
            agent.bump_version(output_contract=new_contract),
            "output_contract",
            what_changed,
            why,
        )
