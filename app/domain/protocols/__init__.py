"""Domain protocol interfaces (ports) for external adapters and persistence."""

from app.domain.protocols.cache import CacheProtocol
from app.domain.protocols.document_parser import DocumentParserProtocol
from app.domain.protocols.llm_gateway import (
    EmbeddingGatewayProtocol,
    LLMGatewayProtocol,
    LLMResponse,
)
from app.domain.protocols.repositories import (
    AgentRepositoryProtocol,
    ChatRepositoryProtocol,
    DocumentRepositoryProtocol,
    EvalRepositoryProtocol,
    ProjectRepositoryProtocol,
)
from app.domain.protocols.tool import AgentToolProtocol
from app.domain.protocols.vector_store import VectorStoreProtocol

__all__ = [
    "AgentRepositoryProtocol",
    "AgentToolProtocol",
    "CacheProtocol",
    "ChatRepositoryProtocol",
    "DocumentParserProtocol",
    "DocumentRepositoryProtocol",
    "EmbeddingGatewayProtocol",
    "EvalRepositoryProtocol",
    "LLMGatewayProtocol",
    "LLMResponse",
    "ProjectRepositoryProtocol",
    "VectorStoreProtocol",
]
