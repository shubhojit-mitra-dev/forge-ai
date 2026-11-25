"""Document upload and ingestion routes."""

import hashlib
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, UploadFile, status

from app.application.dtos.project_dtos import DocumentSummaryDTO
from app.domain.entities.document import Document
from app.domain.exceptions import ValidationDomainError
from app.presentation.dependencies import (
    CurrentUserDep,
    DocumentRepoDep,
    DocumentServiceDep,
    ProjectRepoDep,
    StorageAdapterDep,
)
from app.presentation.routes._mappers import require_owned_project

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])


@router.post("", response_model=DocumentSummaryDTO, status_code=status.HTTP_201_CREATED)
async def upload_document(
    project_id: UUID,
    file: Annotated[UploadFile, File()],
    current_user: CurrentUserDep,
    project_repo: ProjectRepoDep,
    document_repo: DocumentRepoDep,
    storage_adapter: StorageAdapterDep,
    document_service: DocumentServiceDep,
) -> DocumentSummaryDTO:
    """Upload a document to Supabase Storage, persist metadata, and index chunks."""
    await require_owned_project(project_repo, project_id, current_user.user_id)

    filename = file.filename or "document.txt"
    mime_type = file.content_type or "application/octet-stream"
    content = await file.read()
    if not content:
        raise ValidationDomainError("EMPTY_DOCUMENT", "Uploaded document cannot be empty.")

    content_hash = hashlib.sha256(content).hexdigest()
    existing = await document_repo.get_by_hash(project_id, content_hash)
    if existing is not None:
        return DocumentSummaryDTO(
            document_id=existing.id,
            filename=existing.filename,
            chunk_count=int(existing.metadata.get("chunk_count", 0)),
        )

    doc_id = uuid4()
    storage_path = f"{project_id}/{doc_id}/{filename}"
    await storage_adapter.upload(storage_path, content, content_type=mime_type)

    chunks = await document_service.ingest_document(
        project_id=project_id,
        document_id=doc_id,
        filename=filename,
        mime_type=mime_type,
        content=content,
    )

    document = Document(
        id=doc_id,
        project_id=project_id,
        filename=filename,
        mime_type=mime_type,
        storage_path=storage_path,
        content_hash=content_hash,
        metadata={"chunk_count": len(chunks)},
    )
    saved = await document_repo.create(document)
    return DocumentSummaryDTO(
        document_id=saved.id,
        filename=saved.filename,
        chunk_count=len(chunks),
    )
