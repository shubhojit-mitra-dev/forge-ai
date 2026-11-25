"""ForgeAI CLI runner (`forge` and `chat` subcommands)."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID, uuid4

from app.application.container import AppContainer, build_container
from app.application.services.agent_generator import AgentGeneratorService
from app.application.services.document_service import DocumentService
from app.application.services.eval_generator import EvalGeneratorService
from app.application.services.groundability_service import GroundabilityService
from app.application.services.intake_service import IntakeService
from app.application.services.pipeline_orchestrator import PipelineOrchestrator
from app.domain.entities.agent_definition import (
    AgentDefinition,
    OutputContract,
    RetrievalConfig,
)
from app.domain.entities.project import ForgeProject
from app.domain.entities.requirements import ClarifyingQA, RequirementsDoc
from app.domain.value_objects.enums import RunStatus, ToolName
from app.infrastructure.supabase import (
    PgVectorStore,
    SupabaseAgentRepository,
    SupabaseEvalRepository,
    SupabaseProjectRepository,
    get_supabase_client,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.entities.document import DocumentChunk
    from app.domain.entities.evaluation import EvalCase, HonestReport, IterationLog, JudgeScore
    from app.domain.protocols.repositories import (
        AgentRepositoryProtocol,
        EvalRepositoryProtocol,
        ProjectRepositoryProtocol,
    )
    from app.domain.protocols.vector_store import VectorStoreProtocol

_SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}


def _to_jsonable(value: Any) -> Any:
    """Recursively convert domain dataclasses, UUIDs, Enums, and datetimes to JSON types."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(_to_jsonable(payload), indent=2) + "\n", encoding="utf-8")


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class _InMemoryVectorStore:
    """Local CLI in-memory hybrid vector + keyword store implementing VectorStoreProtocol."""

    def __init__(self) -> None:
        self._chunks: list[DocumentChunk] = []

    async def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
        existing_ids = {c.id for c in chunks}
        self._chunks = [c for c in self._chunks if c.id not in existing_ids]
        self._chunks.extend(chunks)

    async def hybrid_search(
        self,
        project_id: UUID,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 5,
        similarity_threshold: float = 0.35,
    ) -> list[DocumentChunk]:
        project_chunks = [c for c in self._chunks if c.project_id == project_id]
        if not project_chunks:
            return []

        query_terms = {term for term in query_text.lower().split() if len(term) >= 2}
        scored: list[tuple[float, DocumentChunk]] = []

        for chunk in project_chunks:
            cos_sim = (
                _cosine_similarity(query_embedding, chunk.embedding)
                if chunk.embedding is not None
                else 0.0
            )
            if query_terms:
                content_lower = chunk.content.lower()
                matches = sum(1 for term in query_terms if term in content_lower)
                kw_score = matches / len(query_terms)
            else:
                kw_score = 0.0

            combined = (0.7 * cos_sim) + (0.3 * kw_score)
            chunk.similarity = cos_sim
            chunk.rrf_score = combined
            if cos_sim >= similarity_threshold or kw_score > 0.0:
                scored.append((combined, chunk))

        if not scored:
            scored = [(c.rrf_score, c) for c in project_chunks]

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]


class _InMemoryProjectRepo:
    """In-memory ProjectRepositoryProtocol for local CLI execution."""

    def __init__(self) -> None:
        self._projects: dict[UUID, ForgeProject] = {}

    async def create(self, project: ForgeProject) -> ForgeProject:
        self._projects[project.id] = project
        return project

    async def get_by_id(self, project_id: UUID) -> ForgeProject | None:
        return self._projects.get(project_id)

    async def list_by_user(self, user_id: UUID) -> list[ForgeProject]:
        return [p for p in self._projects.values() if p.user_id == user_id]

    async def update(self, project: ForgeProject) -> ForgeProject:
        self._projects[project.id] = project
        return project


class _InMemoryAgentRepo:
    """In-memory AgentRepositoryProtocol for local CLI execution."""

    def __init__(self) -> None:
        self._versions: list[AgentDefinition] = []

    async def save(self, agent: AgentDefinition) -> AgentDefinition:
        self._versions.append(agent)
        return agent

    async def get_latest(self, project_id: UUID) -> AgentDefinition | None:
        matching = [a for a in self._versions if a.project_id == project_id]
        return max(matching, key=lambda a: a.version) if matching else None

    async def get_by_slug(self, slug: str) -> AgentDefinition | None:
        matching = [a for a in self._versions if a.slug == slug]
        return max(matching, key=lambda a: a.version) if matching else None

    async def list_versions(self, project_id: UUID) -> list[AgentDefinition]:
        return sorted(
            [a for a in self._versions if a.project_id == project_id],
            key=lambda a: a.version,
        )


class _InMemoryEvalRepo:
    """In-memory EvalRepositoryProtocol for local CLI execution."""

    def __init__(self) -> None:
        self._cases: dict[UUID, list[EvalCase]] = {}
        self._scores: dict[tuple[UUID, int], list[JudgeScore]] = {}
        self._logs: dict[UUID, list[IterationLog]] = {}
        self._reports: dict[UUID, HonestReport] = {}

    async def save_eval_cases(self, project_id: UUID, cases: list[EvalCase]) -> None:
        self._cases[project_id] = list(cases)

    async def list_eval_cases(self, project_id: UUID) -> list[EvalCase]:
        return list(self._cases.get(project_id, []))

    async def save_judge_scores(
        self,
        project_id: UUID,
        iteration: int,
        scores: list[JudgeScore],
    ) -> None:
        self._scores[(project_id, iteration)] = list(scores)

    async def save_iteration_log(self, project_id: UUID, log: IterationLog) -> None:
        self._logs.setdefault(project_id, []).append(log)

    async def list_iteration_logs(self, project_id: UUID) -> list[IterationLog]:
        return list(self._logs.get(project_id, []))

    async def save_honest_report(self, report: HonestReport) -> None:
        self._reports[report.project_id] = report

    async def get_honest_report(self, project_id: UUID) -> HonestReport | None:
        return self._reports.get(project_id)


class _BoundAgentGenerator:
    """Adapts AgentGeneratorService to PipelineOrchestrator's AgentGeneratorProtocol."""

    def __init__(self, service: AgentGeneratorService, doc_summaries: list[str]) -> None:
        self._service = service
        self._doc_summaries = doc_summaries

    async def generate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
        slug: str | None = None,
    ) -> AgentDefinition:
        return await self._service.generate(
            project_id=project_id,
            requirements=requirements,
            doc_summaries=self._doc_summaries,
            slug=slug,
        )


class _BoundEvalGenerator:
    """Adapts EvalGeneratorService to PipelineOrchestrator's EvalGeneratorProtocol."""

    def __init__(self, service: EvalGeneratorService, chunks: list[DocumentChunk]) -> None:
        self._service = service
        self._chunks = chunks

    async def generate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
        chunks: list[DocumentChunk] | None = None,
    ) -> list[EvalCase]:
        target_chunks = chunks if chunks is not None else self._chunks
        return await self._service.generate(
            project_id=project_id,
            requirements=requirements,
            chunks=target_chunks,
        )


def _read_brief(brief_arg: str) -> str:
    candidate = Path(brief_arg)
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8").strip()
    return brief_arg.strip()


def _load_docs_from_disk(docs_dir: Path) -> list[tuple[str, str, bytes]]:
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"Documents directory not found: {docs_dir}")
    loaded: list[tuple[str, str, bytes]] = []
    for file_path in sorted(docs_dir.iterdir()):
        if not file_path.is_file():
            continue
        mime_type = _SUPPORTED_EXTENSIONS.get(file_path.suffix.lower())
        if mime_type is None:
            continue
        loaded.append((file_path.name, mime_type, file_path.read_bytes()))
    return loaded


async def _ingest_docs_folder(
    *,
    docs_dir: Path,
    project_id: UUID,
    doc_service: DocumentService,
    chunk_size: int = 600,
    chunk_overlap: int = 100,
) -> tuple[list[DocumentChunk], list[str]]:
    raw_docs = _load_docs_from_disk(docs_dir)
    all_chunks: list[DocumentChunk] = []
    doc_summaries: list[str] = []

    for filename, mime_type, raw_bytes in raw_docs:
        chunks = await doc_service.ingest_document(
            project_id=project_id,
            document_id=uuid4(),
            filename=filename,
            mime_type=mime_type,
            content=raw_bytes,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        all_chunks.extend(chunks)
        if chunks:
            preview = chunks[0].content[:280].replace("\n", " ")
            doc_summaries.append(f"{filename}: {preview}")

    return all_chunks, doc_summaries


def _resolve_qa_pairs(
    questions: list[str],
    answers_path: Path | None,
    non_interactive: bool,
) -> list[ClarifyingQA]:
    if answers_path is not None:
        raw = json.loads(answers_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "answers" in raw:
            raw = raw["answers"]
        qa_pairs: list[ClarifyingQA] = []
        if isinstance(raw, list):
            for idx, question in enumerate(questions):
                if idx < len(raw):
                    item = raw[idx]
                    if isinstance(item, dict):
                        ans = str(item.get("answer", "")).strip()
                    else:
                        ans = str(item).strip()
                else:
                    ans = "No additional clarification provided."
                qa_pairs.append(ClarifyingQA(question=question, answer=ans or "N/A"))
            return qa_pairs

    if non_interactive:
        return [
            ClarifyingQA(question=q, answer="No additional clarification provided.")
            for q in questions
        ]

    interactive_pairs: list[ClarifyingQA] = []
    for idx, question in enumerate(questions, start=1):
        try:
            answer = input(f"[{idx}/{len(questions)}] {question}\n> ").strip()
        except EOFError:
            answer = ""
        interactive_pairs.append(
            ClarifyingQA(
                question=question,
                answer=answer or "No additional clarification provided.",
            )
        )
    return interactive_pairs


def _render_honest_report_md(
    report: HonestReport,
    agent: AgentDefinition | None,
    iteration_logs: Sequence[IterationLog],
) -> str:
    agent_label = agent.slug if agent is not None else str(report.project_id)
    lines = [
        f"# ForgeAI Honest Quality Report — `{agent_label}` (v{report.final_agent_version})",
        "",
        f"- **Project ID:** `{report.project_id}`",
        f"- **Final Pass Rate:** {report.final_pass_rate:.1%}",
        f"- **Recommendation:** {report.recommendation}",
        "",
        "## Per-Iteration Scorecard",
        "",
        "| Iteration | Score Before | Score After | Delta | Failures Addressed | Change |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    logs_by_iter = {log.iteration: log for log in iteration_logs}
    for row in report.per_iteration_scores:
        it = int(row.get("iteration", 0))
        log = logs_by_iter.get(it)
        change_desc = f"{log.change_type}: {log.what_changed}" if log else "-"
        lines.append(
            f"| {it} | {float(row.get('score_before', 0.0)):.1%} | "
            f"{float(row.get('score_after', 0.0)):.1%} | "
            f"{float(row.get('delta', 0.0)):+.1%} | "
            f"{int(row.get('failures_addressed', 0))} | {change_desc} |"
        )

    lines.extend(["", "## Remaining Failures", ""])
    if not report.remaining_failures:
        lines.append("None — all evaluation cases passed.")
    else:
        for failure in report.remaining_failures:
            lines.append(
                f"- **[{failure.get('failure_category', 'unknown')}]** "
                f"{failure.get('question', '')} — {failure.get('reasoning', '')}"
            )

    lines.extend(["", "## Known Limitations", ""])
    if not report.known_limitations:
        lines.append("No additional limitations recorded.")
    else:
        for limitation in report.known_limitations:
            lines.append(f"- {limitation}")

    return "\n".join(lines) + "\n"


def _load_agent_definition(agent_path: Path) -> AgentDefinition:
    raw = json.loads(agent_path.read_text(encoding="utf-8"))
    rc_raw = raw.get("retrieval_config", {})
    oc_raw = raw.get("output_contract", {})
    fmt = oc_raw.get("format", "markdown")
    output_format: Literal["markdown", "json"] = "json" if fmt == "json" else "markdown"

    return AgentDefinition(
        id=UUID(str(raw["id"])),
        project_id=UUID(str(raw["project_id"])),
        slug=str(raw["slug"]),
        version=int(raw["version"]),
        system_prompt=str(raw["system_prompt"]),
        retrieval_config=RetrievalConfig(
            chunk_size=int(rc_raw.get("chunk_size", 600)),
            chunk_overlap=int(rc_raw.get("chunk_overlap", 100)),
            top_k=int(rc_raw.get("top_k", 5)),
            similarity_threshold=float(rc_raw.get("similarity_threshold", 0.35)),
            hybrid_search=bool(rc_raw.get("hybrid_search", True)),
        ),
        selected_tools=[ToolName(str(t)) for t in raw.get("selected_tools", [])],
        output_contract=OutputContract(
            format=output_format,
            require_citations=bool(oc_raw.get("require_citations", True)),
            refusal_template=str(
                oc_raw.get(
                    "refusal_template",
                    "I cannot answer this based on the provided documents.",
                )
            ),
            max_response_words=int(oc_raw.get("max_response_words", 350)),
        ),
        is_published=bool(raw.get("is_published", False)),
    )


def _wire_storage_and_repos(
    *,
    container: AppContainer,
    use_supabase: bool,
) -> tuple[
    VectorStoreProtocol,
    ProjectRepositoryProtocol,
    AgentRepositoryProtocol,
    EvalRepositoryProtocol,
]:
    if use_supabase:
        client = get_supabase_client(container.settings)
        return (
            PgVectorStore(client),
            SupabaseProjectRepository(client),
            SupabaseAgentRepository(client),
            SupabaseEvalRepository(client),
        )
    return (
        _InMemoryVectorStore(),
        _InMemoryProjectRepo(),
        _InMemoryAgentRepo(),
        _InMemoryEvalRepo(),
    )


def _ensure_out_dir(out_arg: str) -> Path:
    out_dir = Path(out_arg)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


async def run_forge(args: argparse.Namespace) -> int:
    """Execute the full unattended ForgeAI factory pipeline and write 7 artifacts."""
    container = build_container()
    vector_store, project_repo, agent_repo, eval_repo = _wire_storage_and_repos(
        container=container,
        use_supabase=bool(args.use_supabase),
    )

    project_id = uuid4()
    user_id = UUID(args.user_id) if args.user_id else uuid4()
    brief = _read_brief(args.brief)
    out_dir = _ensure_out_dir(args.out)

    doc_service = DocumentService(
        parsers=[container.parsers.pdf, container.parsers.csv, container.parsers.text],
        chunker=container.parsers.chunker,
        embedding_gateway=container.embedding_gateway,
        vector_store=vector_store,
    )
    chunks, doc_summaries = await _ingest_docs_folder(
        docs_dir=Path(args.docs),
        project_id=project_id,
        doc_service=doc_service,
    )

    intake = IntakeService(llm_gateway=container.llm_gateway)
    questions = await intake.generate_questions(brief=brief, doc_summaries=doc_summaries)
    answers_path = Path(args.answers) if args.answers else None
    qa_pairs = _resolve_qa_pairs(
        questions=questions,
        answers_path=answers_path,
        non_interactive=bool(args.non_interactive),
    )
    requirements = await intake.finalize_requirements(
        brief=brief,
        doc_summaries=doc_summaries,
        qa_pairs=qa_pairs,
    )
    _write_json(out_dir / "requirements_doc.json", requirements)

    groundability = GroundabilityService(
        embedding_gateway=container.embedding_gateway,
        vector_store=vector_store,
        llm_gateway=container.llm_gateway,
    )
    groundability_report = await groundability.evaluate(
        project_id=project_id,
        requirements=requirements,
    )
    _write_json(out_dir / "groundability_report.json", groundability_report)

    if not groundability_report.is_passable:
        print(
            f"Groundability guard blocked generation: {groundability_report.summary}",
            file=sys.stderr,
        )
        return 2

    project = ForgeProject(
        id=project_id,
        user_id=user_id,
        title=args.project_title,
        brief=brief,
        status=RunStatus.PENDING,
        requirements_doc=requirements,
        groundability_report=groundability_report,
    )
    await project_repo.create(project)

    agent_gen = _BoundAgentGenerator(
        AgentGeneratorService(
            llm_gateway=container.llm_gateway,
            tool_registry=container.tool_registry,
        ),
        doc_summaries=doc_summaries,
    )
    eval_gen = _BoundEvalGenerator(
        EvalGeneratorService(llm_gateway=container.llm_gateway),
        chunks=chunks,
    )

    orchestrator = PipelineOrchestrator(
        agent_generator=agent_gen,
        eval_generator=eval_gen,
        llm_gateway=container.llm_gateway,
        embedding_gateway=container.embedding_gateway,
        vector_store=vector_store,
        judge_service=container.judge_service,
        critic_optimizer=container.critic_optimizer,
        reporter_service=container.reporter_service,
        project_repo=project_repo,
        agent_repo=agent_repo,
        eval_repo=eval_repo,
        max_llm_calls=container.settings.forge_max_llm_calls_per_run,
    )

    report = await orchestrator.run(project_id=project_id)
    final_agent = await agent_repo.get_latest(project_id)
    eval_cases = await eval_repo.list_eval_cases(project_id)
    iteration_logs = await eval_repo.list_iteration_logs(project_id)

    _write_json(out_dir / "agent_definition.json", final_agent)
    _write_json(out_dir / "eval_set.json", eval_cases)
    _write_json(out_dir / "iteration_logs.json", iteration_logs)
    _write_json(
        out_dir / "scorecard.json",
        {
            "project_id": str(report.project_id),
            "final_agent_version": report.final_agent_version,
            "final_pass_rate": report.final_pass_rate,
            "per_iteration_scores": report.per_iteration_scores,
            "remaining_failures": report.remaining_failures,
            "known_limitations": report.known_limitations,
            "recommendation": report.recommendation,
        },
    )
    (out_dir / "honest_report.md").write_text(
        _render_honest_report_md(report, final_agent, iteration_logs),
        encoding="utf-8",
    )
    return 0


async def _answer_chat_turn(
    *,
    agent: AgentDefinition,
    query: str,
    container: AppContainer,
    vector_store: VectorStoreProtocol | None,
) -> str:
    context_block = ""
    if vector_store is not None:
        vectors = await container.embedding_gateway.embed_texts([query])
        query_embedding = vectors[0] if vectors else []
        chunks = await vector_store.hybrid_search(
            project_id=agent.project_id,
            query_text=query,
            query_embedding=query_embedding,
            top_k=agent.retrieval_config.top_k,
            similarity_threshold=agent.retrieval_config.similarity_threshold,
        )
        context_block = "\n\n".join(
            f"[{c.metadata.get('filename', 'source')}] {c.content}" for c in chunks
        )

    user_content = (
        f"Context:\n{context_block or '(No context retrieved)'}\n\nQuestion: {query}"
        if vector_store is not None
        else query
    )
    resp = await container.llm_gateway.complete(
        messages=[
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": user_content},
        ],
        tier="orchestrator-primary",
        temperature=0.0,
        max_tokens=1024,
    )
    return resp.content


async def run_chat(args: argparse.Namespace) -> int:
    """Load an AgentDefinition JSON and run single-turn or interactive chat."""
    container = build_container()
    agent = _load_agent_definition(Path(args.agent))

    vector_store: _InMemoryVectorStore | None = None
    if args.docs:
        vector_store = _InMemoryVectorStore()
        doc_service = DocumentService(
            parsers=[container.parsers.pdf, container.parsers.csv, container.parsers.text],
            chunker=container.parsers.chunker,
            embedding_gateway=container.embedding_gateway,
            vector_store=vector_store,
        )
        await _ingest_docs_folder(
            docs_dir=Path(args.docs),
            project_id=agent.project_id,
            doc_service=doc_service,
            chunk_size=agent.retrieval_config.chunk_size,
            chunk_overlap=agent.retrieval_config.chunk_overlap,
        )

    if args.query:
        reply = await _answer_chat_turn(
            agent=agent,
            query=str(args.query),
            container=container,
            vector_store=vector_store,
        )
        print(reply)
        return 0

    print(f"Loaded agent '{agent.slug}' (v{agent.version}). Type 'exit' or 'quit' to stop.")
    while True:
        try:
            user_input = (await asyncio.to_thread(input, "> ")).strip()
        except EOFError:
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        reply = await _answer_chat_turn(
            agent=agent,
            query=user_input,
            container=container,
            vector_store=vector_store,
        )
        print(reply)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the ForgeAI CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="forge-ai",
        description="ForgeAI unattended agent factory and chat runner CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    forge_parser = subparsers.add_parser("forge", help="Run the full ForgeAI factory pipeline.")
    forge_parser.add_argument("--brief", required=True, help="Brief text or path to a brief file.")
    forge_parser.add_argument("--docs", required=True, help="Folder path of PDF/CSV/MD/TXT docs.")
    forge_parser.add_argument("--out", required=True, help="Output directory for artifacts.")
    forge_parser.add_argument(
        "--answers",
        default=None,
        help="Optional JSON file containing clarifying Q&A answers.",
    )
    forge_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use default answers when --answers is omitted so unattended runs never hang.",
    )
    forge_parser.add_argument(
        "--use-supabase",
        action="store_true",
        help="Persist to Supabase + PgVector instead of local in-memory stores.",
    )
    forge_parser.add_argument(
        "--project-title",
        default="CLI Forge Project",
        help="Optional project title.",
    )
    forge_parser.add_argument(
        "--user-id",
        default=None,
        help="Optional user UUID for Supabase persistence.",
    )

    chat_parser = subparsers.add_parser("chat", help="Run a generated agent from JSON.")
    chat_parser.add_argument("--agent", required=True, help="Path to agent_definition.json.")
    chat_parser.add_argument("--docs", default=None, help="Optional docs folder for local RAG.")
    chat_parser.add_argument(
        "--query",
        default=None,
        help="Single-turn query (omit for interactive stdin loop).",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint returning process exit code."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "forge":
        return asyncio.run(run_forge(args))
    if args.command == "chat":
        return asyncio.run(run_chat(args))
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(cast("Sequence[str] | None", sys.argv[1:])))
