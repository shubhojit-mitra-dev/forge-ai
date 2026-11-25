"""FastAPI dependency injection providers and Annotated type aliases."""

import importlib
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.container import AppContainer, build_container
from app.application.services.agent_generator import AgentGeneratorService
from app.application.services.chat_runner_service import ChatRunnerService
from app.application.services.document_service import DocumentService
from app.application.services.eval_generator import EvalGeneratorService
from app.application.services.groundability_service import GroundabilityService
from app.application.services.intake_service import IntakeService
from app.application.services.pipeline_orchestrator import PipelineOrchestrator
from app.domain.entities.agent_definition import AgentDefinition
from app.domain.entities.document import DocumentChunk
from app.domain.entities.evaluation import EvalCase
from app.domain.entities.requirements import RequirementsDoc
from app.domain.protocols.repositories import (
    AgentRepositoryProtocol,
    ChatRepositoryProtocol,
    DocumentRepositoryProtocol,
    EvalRepositoryProtocol,
    ProjectRepositoryProtocol,
)
from app.domain.protocols.vector_store import VectorStoreProtocol
from app.infrastructure.supabase.client import get_supabase_client
from app.infrastructure.supabase.pgvector_store import PgVectorStore
from app.infrastructure.supabase.repositories.agent_repo import SupabaseAgentRepository
from app.infrastructure.supabase.repositories.chat_repo import SupabaseChatRepository
from app.infrastructure.supabase.repositories.document_repo import SupabaseDocumentRepository
from app.infrastructure.supabase.repositories.eval_repo import SupabaseEvalRepository
from app.infrastructure.supabase.repositories.project_repo import SupabaseProjectRepository
from app.infrastructure.supabase.storage import SupabaseStorageAdapter

if TYPE_CHECKING:
    from supabase import Client


@dataclass(slots=True, frozen=True)
class UserContext:
    """Authenticated user identity extracted from a verified Supabase JWT."""

    user_id: UUID
    email: str | None = None
    role: str = "authenticated"


_bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_container() -> AppContainer:
    """Return the cached singleton AppContainer."""
    return build_container()


ContainerDep = Annotated[AppContainer, Depends(get_container)]


async def get_current_user(
    request: Request,
    container: ContainerDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> UserContext:
    """Verify Supabase JWT and return UserContext, delegating to auth middleware if present."""
    try:
        auth_mod = importlib.import_module("app.presentation.middleware.auth")
        auth_fn = getattr(auth_mod, "get_current_user", None)
        if callable(auth_fn) and auth_fn is not get_current_user:
            resolved = await auth_fn(request=request, credentials=credentials)
            return UserContext(
                user_id=UUID(str(resolved.user_id)),
                email=getattr(resolved, "email", None),
                role=str(getattr(resolved, "role", "authenticated")),
            )
    except ModuleNotFoundError:
        pass

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
        )

    secret = container.settings.supabase_jwt_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT verification secret is not configured.",
        )

    try:
        payload: dict[str, Any] = jwt.decode(
            credentials.credentials,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing 'sub' claim.",
            )
        return UserContext(
            user_id=UUID(str(sub)),
            email=payload.get("email"),
            role=str(payload.get("role", "authenticated")),
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        ) from exc


CurrentUserDep = Annotated[UserContext, Depends(get_current_user)]


def get_supabase_dep(container: ContainerDep) -> "Client":
    """Return the cached Supabase client configured by Settings."""
    return get_supabase_client(container.settings)


SupabaseDep = Annotated["Client", Depends(get_supabase_dep)]


def get_project_repo(client: SupabaseDep) -> ProjectRepositoryProtocol:
    """Provide ProjectRepositoryProtocol backed by Supabase."""
    return SupabaseProjectRepository(client)


def get_document_repo(client: SupabaseDep) -> DocumentRepositoryProtocol:
    """Provide DocumentRepositoryProtocol backed by Supabase."""
    return SupabaseDocumentRepository(client)


def get_agent_repo(client: SupabaseDep) -> AgentRepositoryProtocol:
    """Provide AgentRepositoryProtocol backed by Supabase."""
    return SupabaseAgentRepository(client)


def get_eval_repo(client: SupabaseDep) -> EvalRepositoryProtocol:
    """Provide EvalRepositoryProtocol backed by Supabase."""
    return SupabaseEvalRepository(client)


def get_chat_repo(client: SupabaseDep) -> ChatRepositoryProtocol:
    """Provide ChatRepositoryProtocol backed by Supabase."""
    return SupabaseChatRepository(client)


def get_vector_store(client: SupabaseDep) -> VectorStoreProtocol:
    """Provide VectorStoreProtocol backed by pgvector."""
    return PgVectorStore(client)


def get_storage_adapter(
    container: ContainerDep,
    client: SupabaseDep,
) -> SupabaseStorageAdapter:
    """Provide SupabaseStorageAdapter for the configured bucket."""
    return SupabaseStorageAdapter(
        client=client,
        bucket_name=container.settings.supabase_storage_bucket,
    )


ProjectRepoDep = Annotated[ProjectRepositoryProtocol, Depends(get_project_repo)]
DocumentRepoDep = Annotated[DocumentRepositoryProtocol, Depends(get_document_repo)]
AgentRepoDep = Annotated[AgentRepositoryProtocol, Depends(get_agent_repo)]
EvalRepoDep = Annotated[EvalRepositoryProtocol, Depends(get_eval_repo)]
ChatRepoDep = Annotated[ChatRepositoryProtocol, Depends(get_chat_repo)]
VectorStoreDep = Annotated[VectorStoreProtocol, Depends(get_vector_store)]
StorageAdapterDep = Annotated[SupabaseStorageAdapter, Depends(get_storage_adapter)]


def get_document_service(
    container: ContainerDep,
    vector_store: VectorStoreDep,
) -> DocumentService:
    """Provide DocumentService wired with parsers, embeddings, and vector store."""
    return DocumentService(
        parsers=[
            container.parsers.pdf,
            container.parsers.csv,
            container.parsers.text,
        ],
        chunker=container.parsers.chunker,
        embedding_gateway=container.embedding_gateway,
        vector_store=vector_store,
    )


def get_intake_service(container: ContainerDep) -> IntakeService:
    """Provide Stage 1 IntakeService."""
    return IntakeService(llm_gateway=container.llm_gateway)


def get_groundability_service(
    container: ContainerDep,
    vector_store: VectorStoreDep,
) -> GroundabilityService:
    """Provide Stage 2 GroundabilityService."""
    return GroundabilityService(
        embedding_gateway=container.embedding_gateway,
        vector_store=vector_store,
        llm_gateway=container.llm_gateway,
    )


class _AgentGeneratorAdapter:
    """Adapts AgentGeneratorService to PipelineOrchestrator's AgentGeneratorProtocol."""

    def __init__(self, service: AgentGeneratorService) -> None:
        self._service = service

    async def generate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
        slug: str | None = None,
    ) -> AgentDefinition:
        return await self._service.generate(
            project_id=project_id,
            requirements=requirements,
            doc_summaries=[],
            slug=slug,
        )


class _EvalGeneratorAdapter:
    """Adapts EvalGeneratorService to PipelineOrchestrator's EvalGeneratorProtocol."""

    def __init__(self, service: EvalGeneratorService) -> None:
        self._service = service

    async def generate(
        self,
        project_id: UUID,
        requirements: RequirementsDoc,
        chunks: list[DocumentChunk] | None = None,
    ) -> list[EvalCase]:
        return await self._service.generate(
            project_id=project_id,
            requirements=requirements,
            chunks=chunks or [],
        )


def get_pipeline_orchestrator(
    container: ContainerDep,
    vector_store: VectorStoreDep,
    project_repo: ProjectRepoDep,
    agent_repo: AgentRepoDep,
    eval_repo: EvalRepoDep,
) -> PipelineOrchestrator:
    """Provide end-to-end PipelineOrchestrator for Stages 3-7."""
    return PipelineOrchestrator(
        agent_generator=_AgentGeneratorAdapter(
            AgentGeneratorService(llm_gateway=container.llm_gateway)
        ),
        eval_generator=_EvalGeneratorAdapter(
            EvalGeneratorService(llm_gateway=container.llm_gateway)
        ),
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


def get_chat_runner_service(
    container: ContainerDep,
    vector_store: VectorStoreDep,
) -> ChatRunnerService:
    """Provide runtime ChatRunnerService for published agents."""
    return ChatRunnerService(
        llm_gateway=container.llm_gateway,
        embedding_gateway=container.embedding_gateway,
        vector_store=vector_store,
        tool_registry=container.tool_registry,
    )


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
IntakeServiceDep = Annotated[IntakeService, Depends(get_intake_service)]
GroundabilityServiceDep = Annotated[GroundabilityService, Depends(get_groundability_service)]
PipelineOrchestratorDep = Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)]
ChatRunnerServiceDep = Annotated[ChatRunnerService, Depends(get_chat_runner_service)]
