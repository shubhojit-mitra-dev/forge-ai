"""Supabase Storage adapter for the `forge-documents` bucket."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client


class SupabaseStorageAdapter:
    """Adapter wrapping Supabase Storage operations for uploaded project documents."""

    def __init__(self, client: Client, bucket_name: str = "forge-documents") -> None:
        self._client = client
        self._bucket_name = bucket_name

    async def upload(
        self,
        path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload raw bytes to the configured bucket and return the storage path."""
        await asyncio.to_thread(
            lambda: self._client.storage.from_(self._bucket_name).upload(
                path,
                content,
                file_options={"content-type": content_type, "upsert": "true"},
            )
        )
        return path

    async def download(self, path: str) -> bytes:
        """Download raw bytes from the configured bucket."""
        return await asyncio.to_thread(
            lambda: self._client.storage.from_(self._bucket_name).download(path)
        )

    async def create_signed_url(self, path: str, expires_in: int = 3600) -> str:
        """Create a time-limited signed URL for downloading a stored object."""
        response = await asyncio.to_thread(
            lambda: self._client.storage.from_(self._bucket_name).create_signed_url(
                path, expires_in
            )
        )
        payload = cast("dict[str, Any]", response)
        signed = payload.get("signedURL") or payload.get("signedUrl") or ""
        return str(signed)

    async def delete(self, path: str) -> None:
        """Remove an object from the configured bucket."""
        await asyncio.to_thread(
            lambda: self._client.storage.from_(self._bucket_name).remove([path])
        )
