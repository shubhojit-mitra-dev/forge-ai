from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from app.domain.entities.requirements import GroundabilityReport, RequirementsDoc
from app.domain.value_objects.enums import RunStatus


@dataclass(slots=True)
class ForgeProject:
    """Root aggregate for a ForgeAI agent-building project."""

    id: UUID
    user_id: UUID
    title: str
    brief: str
    status: RunStatus
    requirements_doc: RequirementsDoc | None = None
    groundability_report: GroundabilityReport | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
