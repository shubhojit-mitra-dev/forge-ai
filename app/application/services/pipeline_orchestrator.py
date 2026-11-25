"""End-to-end ForgeAI Pipeline Orchestrator (Stages 3 through 7)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from app.domain.exceptions import EntityNotFoundError, ValidationDomainError
from app.domain.value_objects.enums import RunStatus

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from app.application.services.critic_optimizer import CriticOptimizerService
    from app.application.services.judge_service import JudgeService
    from app.application.services.reporter_service import ReporterService
    from app.domain.entities.agent_definition import AgentDefinition
    from app.domain.entities.document import DocumentChunk
    from app.domain.entities.evaluation import EvalCase, HonestReport, IterationLog, JudgeScore
    from app.domain.entities.requirements import RequirementsDoc
    from app.domain.protocols.llm_gateway import (
        EmbeddingGatewayProtocol,
        LLMGatewayProtocol,
    )
    from app.domain.protocols.repositories import (
        AgentRepositoryProtocol,
        EvalRepositoryProtocol,
        ProjectRepositoryProtocol,
    )
    from app.domain.protocols.vector_store import VectorStoreProtocol


@runtime_checkable
class AgentGeneratorProtocol(Protocol):
    """Port for Stage 3 initial AgentDefinition generation."""

    async def generate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
        slug: str | None = None,
    ) -> AgentDefinition:
        """Generate initial AgentDefinition v1 from RequirementsDoc."""
        ...


@runtime_checkable
class EvalGeneratorProtocol(Protocol):
    """Port for Stage 4 evaluation suite generation."""

    async def generate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
        chunks: list[DocumentChunk] | None = None,
    ) -> list[EvalCase]:
        """Generate grounded evaluation cases for a project."""
        ...


type EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class PipelineOrchestrator:
    """Runs the unattended ForgeAI pipeline: AgentGen -> EvalGen -> Judge/Critic -> Report."""

    def __init__(
        self,
        *,
        agent_generator: AgentGeneratorProtocol,
        eval_generator: EvalGeneratorProtocol,
        llm_gateway: LLMGatewayProtocol,
        embedding_gateway: EmbeddingGatewayProtocol,
        vector_store: VectorStoreProtocol,
        judge_service: JudgeService,
        critic_optimizer: CriticOptimizerService,
        reporter_service: ReporterService,
        project_repo: ProjectRepositoryProtocol,
        agent_repo: AgentRepositoryProtocol,
        eval_repo: EvalRepositoryProtocol,
        agent_tier: str = "orchestrator-primary",
        max_llm_calls: int = 120,
    ) -> None:
        self._agent_generator = agent_generator
        self._eval_generator = eval_generator
        self._llm = llm_gateway
        self._embeddings = embedding_gateway
        self._vector_store = vector_store
        self._judge = judge_service
        self._critic = critic_optimizer
        self._reporter = reporter_service
        self._project_repo = project_repo
        self._agent_repo = agent_repo
        self._eval_repo = eval_repo
        self._agent_tier = agent_tier
        self._max_llm_calls = max_llm_calls

    async def _emit(self, on_event: EventCallback | None, payload: dict[str, Any]) -> None:
        if on_event is not None:
            await on_event(payload)

    async def run(
        self,
        *,
        project_id: UUID,
        on_event: EventCallback | None = None,
    ) -> HonestReport:
        """Execute Stages 3-7 unattended for `project_id` and return HonestReport."""
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise EntityNotFoundError("PROJECT_NOT_FOUND", f"Project {project_id} not found.")
        if project.requirements_doc is None:
            raise ValidationDomainError(
                "MISSING_REQUIREMENTS",
                f"Project {project_id} has no RequirementsDoc; complete intake first.",
            )

        project.status = RunStatus.RUNNING
        await self._project_repo.update(project)

        try:
            await self._emit(on_event, {"event": "stage_started", "stage": "agent_generation"})
            initial_agent = await self._agent_generator.generate(
                project_id=project_id,
                requirements=project.requirements_doc,
            )
            await self._agent_repo.save(initial_agent)

            await self._emit(on_event, {"event": "stage_started", "stage": "eval_generation"})
            eval_cases = await self._eval_generator.generate(
                project_id=project_id,
                requirements=project.requirements_doc,
            )
            await self._eval_repo.save_eval_cases(project_id, eval_cases)

            await self._emit(on_event, {"event": "stage_started", "stage": "optimization"})
            eval_iteration = 0

            async def evaluate_candidate(candidate: AgentDefinition) -> list[JudgeScore]:
                nonlocal eval_iteration
                eval_iteration += 1
                scores: list[JudgeScore] = []
                for case in eval_cases:
                    score = await self._run_single_eval(candidate, case)
                    scores.append(score)
                    await self._emit(
                        on_event,
                        {
                            "event": "eval_scored",
                            "iteration": eval_iteration,
                            "eval_case_id": str(case.id),
                            "passed": score.passed,
                            "failure_category": score.failure_category.value,
                        },
                    )
                await self._eval_repo.save_judge_scores(project_id, eval_iteration, scores)
                return scores

            async def handle_iteration(log: IterationLog) -> None:
                await self._eval_repo.save_iteration_log(project_id, log)
                await self._emit(
                    on_event,
                    {
                        "event": "iteration_complete",
                        "iteration": log.iteration,
                        "score_before": log.score_before,
                        "score_after": log.score_after,
                        "change_type": log.change_type,
                    },
                )

            opt_result = await self._critic.optimize(
                agent=initial_agent,
                evaluate_fn=evaluate_candidate,
                remaining_call_budget=self._max_llm_calls,
                on_iteration=handle_iteration,
            )
            if opt_result.final_agent.version != initial_agent.version:
                await self._agent_repo.save(opt_result.final_agent)

            await self._emit(on_event, {"event": "stage_started", "stage": "reporting"})
            report = self._reporter.compile_report(
                project_id=project_id,
                final_agent=opt_result.final_agent,
                iteration_logs=opt_result.iteration_logs,
                final_scores=opt_result.final_scores,
                eval_cases=eval_cases,
                stop_reason=opt_result.stop_reason,
            )
            await self._eval_repo.save_honest_report(report)

            project.status = (
                RunStatus.STOPPED_EARLY
                if opt_result.stop_reason in {"diminishing_returns", "budget_cap_reached"}
                else RunStatus.COMPLETED
            )
            await self._project_repo.update(project)

            await self._emit(
                on_event,
                {
                    "event": "forge_finished",
                    "final_pass_rate": report.final_pass_rate,
                    "final_agent_version": report.final_agent_version,
                    "stop_reason": opt_result.stop_reason,
                },
            )
            return report
        except Exception:
            project.status = RunStatus.FAILED
            await self._project_repo.update(project)
            raise

    async def _run_single_eval(
        self,
        agent: AgentDefinition,
        eval_case: EvalCase,
    ) -> JudgeScore:
        started = time.monotonic()
        vectors = await self._embeddings.embed_texts([eval_case.question])
        query_embedding = vectors[0] if vectors else []
        chunks = await self._vector_store.hybrid_search(
            project_id=agent.project_id,
            query_text=eval_case.question,
            query_embedding=query_embedding,
            top_k=agent.retrieval_config.top_k,
            similarity_threshold=agent.retrieval_config.similarity_threshold,
        )
        context_block = "\n\n".join(
            f"[{c.metadata.get('filename', 'source')}] {c.content}" for c in chunks
        )
        user_content = (
            f"Context:\n{context_block or '(No context retrieved)'}\n\n"
            f"Question: {eval_case.question}"
        )
        agent_resp = await self._llm.complete(
            messages=[
                {"role": "system", "content": agent.system_prompt},
                {"role": "user", "content": user_content},
            ],
            tier=self._agent_tier,
            temperature=0.0,
            max_tokens=1024,
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        return await self._judge.evaluate_case(
            eval_case=eval_case,
            agent_response=agent_resp.content,
            retrieved_chunks=chunks,
            output_contract=agent.output_contract,
            latency_ms=latency_ms,
        )
