"""Supabase repository implementation for ForgeProject aggregates."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from app.domain.entities.project import ForgeProject
from app.domain.entities.requirements import (
    ClarifyingQA,
    GroundabilityReport,
    RequirementsDoc,
    TopicGroundability,
)
from app.domain.value_objects.enums import RunStatus, ToolName

if TYPE_CHECKING:
    from supabase import Client


class SupabaseProjectRepository:
    """Supabase persistence adapter implementing ProjectRepositoryProtocol."""

    _TABLE = "forge_projects"

    def __init__(self, client: Client) -> None:
        self._client = client

    async def create(self, project: ForgeProject) -> ForgeProject:
        """Persist a new ForgeAI project."""
        payload = self._to_row(project)
        response = await asyncio.to_thread(
            lambda: self._client.table(self._TABLE).insert(payload).execute()
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._from_row(rows[0]) if rows else project

    async def get_by_id(self, project_id: UUID) -> ForgeProject | None:
        """Fetch a project by its unique identifier."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._TABLE)
                .select("*")
                .eq("id", str(project_id))
                .limit(1)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._from_row(rows[0]) if rows else None

    async def list_by_user(self, user_id: UUID) -> list[ForgeProject]:
        """List all projects belonging to a user."""
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._TABLE)
                .select("*")
                .eq("user_id", str(user_id))
                .order("created_at", desc=True)
                .execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return [self._from_row(row) for row in rows]

    async def update(self, project: ForgeProject) -> ForgeProject:
        """Persist updates to an existing project."""
        payload = self._to_row(project)
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self._TABLE).update(payload).eq("id", str(project.id)).execute()
            )
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        return self._from_row(rows[0]) if rows else project

    @staticmethod
    def _to_row(project: ForgeProject) -> dict[str, Any]:
        req_doc: dict[str, Any] | None = None
        if project.requirements_doc is not None:
            r = project.requirements_doc
            req_doc = {
                "agent_name": r.agent_name,
                "scope": r.scope,
                "target_audience": r.target_audience,
                "tone": r.tone,
                "must_answer_topics": list(r.must_answer_topics),
                "must_refuse_topics": list(r.must_refuse_topics),
                "clarifying_qa": [
                    {"question": qa.question, "answer": qa.answer} for qa in r.clarifying_qa
                ],
                "detected_tool_needs": [tool.value for tool in r.detected_tool_needs],
            }

        ground_report: dict[str, Any] | None = None
        if project.groundability_report is not None:
            g = project.groundability_report
            ground_report = {
                "is_passable": g.is_passable,
                "critical_gaps": [
                    {
                        "topic": gap.topic,
                        "is_grounded": gap.is_grounded,
                        "confidence": gap.confidence,
                        "supporting_documents": list(gap.supporting_documents),
                        "gap_reason": gap.gap_reason,
                    }
                    for gap in g.critical_gaps
                ],
                "warnings": [
                    {
                        "topic": warn.topic,
                        "is_grounded": warn.is_grounded,
                        "confidence": warn.confidence,
                        "supporting_documents": list(warn.supporting_documents),
                        "gap_reason": warn.gap_reason,
                    }
                    for warn in g.warnings
                ],
                "summary": g.summary,
            }

        return {
            "id": str(project.id),
            "user_id": str(project.user_id),
            "title": project.title,
            "brief": project.brief,
            "status": project.status.value,
            "requirements_doc": req_doc,
            "groundability_report": ground_report,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
        }

    @staticmethod
    def _from_row(row: dict[str, Any]) -> ForgeProject:
        req_raw = cast("dict[str, Any] | None", row.get("requirements_doc"))
        req_doc: RequirementsDoc | None = None
        if req_raw is not None:
            req_doc = RequirementsDoc(
                agent_name=str(req_raw["agent_name"]),
                scope=str(req_raw["scope"]),
                target_audience=str(req_raw["target_audience"]),
                tone=str(req_raw["tone"]),
                must_answer_topics=list(req_raw.get("must_answer_topics", [])),
                must_refuse_topics=list(req_raw.get("must_refuse_topics", [])),
                clarifying_qa=[
                    ClarifyingQA(question=str(qa["question"]), answer=str(qa["answer"]))
                    for qa in req_raw.get("clarifying_qa", [])
                ],
                detected_tool_needs=[
                    ToolName(str(t)) for t in req_raw.get("detected_tool_needs", [])
                ],
            )

        ground_raw = cast("dict[str, Any] | None", row.get("groundability_report"))
        ground_report: GroundabilityReport | None = None
        if ground_raw is not None:
            ground_report = GroundabilityReport(
                is_passable=bool(ground_raw["is_passable"]),
                critical_gaps=[_topic_from_dict(g) for g in ground_raw.get("critical_gaps", [])],
                warnings=[_topic_from_dict(w) for w in ground_raw.get("warnings", [])],
                summary=str(ground_raw.get("summary", "")),
            )

        return ForgeProject(
            id=UUID(str(row["id"])),
            user_id=UUID(str(row["user_id"])),
            title=str(row["title"]),
            brief=str(row["brief"]),
            status=RunStatus(str(row["status"])),
            requirements_doc=req_doc,
            groundability_report=ground_report,
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )


def _topic_from_dict(data: dict[str, Any]) -> TopicGroundability:
    return TopicGroundability(
        topic=str(data["topic"]),
        is_grounded=bool(data["is_grounded"]),
        confidence=float(data["confidence"]),
        supporting_documents=list(data.get("supporting_documents", [])),
        gap_reason=cast("str | None", data.get("gap_reason")),
    )
