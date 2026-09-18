"""Local file storage for visual assets (owned by REVAMP-P04)."""

from __future__ import annotations

import asyncio
from pathlib import Path


class LocalStorage:
    """Content refs are relative paths under one root; traversal refused."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _resolve(self, content_ref: str) -> Path:
        candidate = (self._root / content_ref).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ValueError(f"content ref escapes storage root: {content_ref}")
        return candidate

    async def read(self, content_ref: str) -> bytes:
        return await asyncio.to_thread(self._resolve(content_ref).read_bytes)

    async def write(self, content_ref: str, data: bytes, mime: str) -> None:
        del mime
        path = self._resolve(content_ref)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)

    async def exists(self, content_ref: str) -> bool:
        return await asyncio.to_thread(self._resolve(content_ref).exists)
