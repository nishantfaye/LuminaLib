
"""Local filesystem storage adapter."""

import logging
from pathlib import Path
from uuid import UUID

import aiofiles
import aiofiles.os

from app.ports.storage import StoragePort

logger = logging.getLogger(__name__)


class LocalStorageAdapter(StoragePort):
    """Store book files on the local filesystem."""

    def __init__(self, base_path: str) -> None:
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)
        logger.info("LocalStorage initialized at: %s", self._base.resolve())

    async def save(self, file_id: UUID, content: bytes, extension: str) -> str:
        """Save file to local disk. Returns absolute path."""
        filename = f"{file_id}.{extension}"
        filepath = self._base / filename
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(content)
        logger.info("Saved file: %s (%d bytes)", filename, len(content))
        return str(filepath)

    async def read(self, path: str) -> bytes:
        """Read file content from local disk."""
        async with aiofiles.open(path, "rb") as f:
            content = await f.read()
        logger.debug("Read file: %s (%d bytes)", path, len(content))
        return content

    async def delete(self, path: str) -> None:
        """Delete file from local disk."""
        target = Path(path)
        if target.exists():
            await aiofiles.os.remove(str(target))
            logger.info("Deleted file: %s", path)
        else:
            logger.warning("File not found for deletion: %s", path)
