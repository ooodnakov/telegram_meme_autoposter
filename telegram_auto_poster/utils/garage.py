"""Minimal local object storage emulating a subset of Garage behaviour."""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator

from loguru import logger


@dataclass
class GarageCopySource:
    bucket_name: str
    object_name: str


class GarageClient:
    """File-system backed object storage used for tests and local runs."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # Bucket helpers ---------------------------------------------------------
    async def bucket_exists(self, bucket_name: str) -> bool:
        return await asyncio.to_thread(self._bucket_path(bucket_name).exists)

    async def make_bucket(self, bucket_name: str) -> None:
        await asyncio.to_thread(
            self._bucket_path(bucket_name).mkdir, parents=True, exist_ok=True
        )

    # Object helpers ---------------------------------------------------------
    async def fput_object(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        *_,
        **__,
    ) -> None:
        destination = self._object_path(bucket_name, object_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._copy_file, Path(file_path), destination)

    async def fget_object(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        *_,
        **__,
    ) -> None:
        source = self._object_path(bucket_name, object_name)
        await asyncio.to_thread(self._copy_file, source, Path(file_path))

    async def get_object(self, bucket_name: str, object_name: str, *_, **__) -> Any:
        path = self._object_path(bucket_name, object_name)
        data = await asyncio.to_thread(path.read_bytes)

        async def _read() -> bytes:
            return data

        async def _close() -> None:
            return None

        async def _release() -> None:
            return None

        return SimpleNamespace(read=_read, close=_close, release_conn=_release)

    async def remove_object(
        self,
        bucket_name: str,
        object_name: str,
        *_,
        **__,
    ) -> None:
        path = self._object_path(bucket_name, object_name)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:  # pragma: no cover - best effort
            logger.debug("Attempted to delete missing object %s", object_name)

    async def stat_object(self, bucket_name: str, object_name: str, *_, **__) -> Any:
        path = self._object_path(bucket_name, object_name)
        if not path.exists():
            raise FileNotFoundError(object_name)
        metadata = {"size": path.stat().st_size}
        return SimpleNamespace(metadata=metadata)

    async def copy_object(
        self,
        bucket_name: str,
        object_name: str,
        source: GarageCopySource,
        *_,
        **__,
    ) -> None:
        src_path = self._object_path(source.bucket_name, source.object_name)
        dest_path = self._object_path(bucket_name, object_name)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._copy_file, src_path, dest_path)

    async def presigned_get_object(
        self,
        bucket_name: str,
        object_name: str,
        *_,
        **__,
    ) -> str:
        return str(self._object_path(bucket_name, object_name).resolve())

    async def list_objects(
        self,
        bucket_name: str,
        prefix: str | None = None,
        recursive: bool = True,
        *_,
        **__,
    ) -> AsyncIterator[SimpleNamespace]:
        base = self._bucket_path(bucket_name)
        if not base.exists():
            return
        iterator = base.rglob("*") if recursive else base.glob("*")
        for path in sorted(iterator):
            if not path.is_file():
                continue
            rel = path.relative_to(base).as_posix()
            if prefix and not rel.startswith(prefix):
                continue
            yield SimpleNamespace(object_name=rel)
            await asyncio.sleep(0)

    # Internal helpers -------------------------------------------------------
    def _bucket_path(self, bucket_name: str) -> Path:
        return self.root / bucket_name

    def _object_path(self, bucket_name: str, object_name: str) -> Path:
        return self._bucket_path(bucket_name) / object_name

    @staticmethod
    def _copy_file(src: Path, dest: Path) -> None:
        shutil.copyfile(src, dest)
