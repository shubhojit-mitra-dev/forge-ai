"""Supabase repository implementation for AgentDefinition entities."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from app.domain.entities.agent_definition import (
    AgentDefinition,
    OutputContract,
    RetrievalConfig,
)
from app.domain.value_objects.enums import ToolName

if TYPE_CHECKING:
    from supabase import Client


class SupabaseAgentRepository:
    """Supabase persistence adapter implementing AgentRepositoryProtocol."""

    _TABLE = "agent_definitions"

    def __init__(self, client: Client) -> None:
        self._client = client

    async def save(self, agent: AgentDefinition) -> AgentDefinition:
        """Persist an agent definition version."""
        payload = self._to_row(agent)
        response = await asyncio.to_thread(
            lambda: self._client.table(self._TABLE).upsert(payload).execute()
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._from_row(rows[0]) if rows else agent

    async def get_latest(self, project_id: UUID) -> AgentDefinition | None:
        """Fetch the latest agent definition version for a project."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._TABLE)
                .select("*")
                .eq("project_id", str(project_id))
                .order("version", desc=True)
                .limit(1)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._from_row(rows[0]) if rows else None

    async def get_by_slug(self, slug: str) -> AgentDefinition | None:
        """Fetch the latest published agent definition by its public slug."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._TABLE)
                .select("*")
                .eq("slug", slug)
                .eq("is_published", True)
                .order("version", desc=True)
                .limit(1)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._from_row(rows[0]) if rows else None

    async def list_versions(self, project_id: UUID) -> list[AgentDefinition]:
        """List all agent definition versions for a project."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._TABLE)
                .select("*")
                .eq("project_id", str(project_id))
                .order("version", desc=False)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _to_row(agent: AgentDefinition) -> dict[str, Any]:
        return {
            "id": str(agent.id),
            "project_id": str(agent.project_id),
            "slug": agent.slug,
            "version": agent.version,
            "system_prompt": agent.system_prompt,
            "retrieval_config": {
                "chunk_size": agent.retrieval_config.chunk_size,
                "chunk_overlap": agent.retrieval_config.chunk_overlap,
                "top_k": agent.retrieval_config.top_k,
                "similarity_threshold": agent.retrieval_config.similarity_threshold,
                "hybrid_search": agent.retrieval_config.hybrid_search,
            },
            "selected_tools": [tool.value for tool in agent.selected_tools],
            "output_contract": {
                "format": agent.output_contract.format,
                "require_citations": agent.output_contract.require_citations,
                "refusal_template": agent.output_contract.refusal_template,
                "max_response_words": agent.output_contract.max_response_words,
            },
            "is_published": agent.is_published,
            "created_at": agent.created_at.isoformat(),
        }

    @staticmethod
    def _from_row(row: dict[str, Any]) -> AgentDefinition:
        rc = cast("dict[str, Any]", row["retrieval_config"])
        oc = cast("dict[str, Any]", row["output_contract"])
        return AgentDefinition(
            id=UUID(str(row["id"])),
            project_id=UUID(str(row["project_id"])),
            slug=str(row["slug"]),
            version=int(row["version"]),
            system_prompt=str(row["system_prompt"]),
            retrieval_config=RetrievalConfig(
                chunk_size=int(rc.get("chunk_size", 600)),
                chunk_overlap=int(rc.get("chunk_overlap", 100)),
                top_k=int(rc.get("top_k", 5)),
                similarity_threshold=float(rc.get("similarity_threshold", 0.35)),
                hybrid_search=bool(rc.get("hybrid_search", True)),
            ),
            selected_tools=[ToolName(str(t)) for t in row.get("selected_tools", [])],
            output_contract=OutputContract(
                format=cast('Literal["markdown", "json"]', str(oc.get("format", "markdown"))),
                require_citations=bool(oc.get("require_citations", True)),
                refusal_template=str(
                    oc.get(
                        "refusal_template",
                        "I cannot answer this based on the provided documents.",
                    )
                ),
                max_response_words=int(oc.get("max_response_words", 350)),
            ),
            is_published=bool(row.get("is_published", False)),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )
