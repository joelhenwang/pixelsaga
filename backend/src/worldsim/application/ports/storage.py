"""Binary storage port (owned by REVAMP-P04).

Content lives outside database rows; references are immutable paths
relative to a configured root. Local files back local deployment.
"""

from __future__ import annotations

from typing import Protocol


class StoragePort(Protocol):
    async def read(self, content_ref: str) -> bytes: ...
    async def write(self, content_ref: str, data: bytes, mime: str) -> None: ...
    async def exists(self, content_ref: str) -> bool: ...
