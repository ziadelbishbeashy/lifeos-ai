"""Secure local-development storage implementation."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from werkzeug.utils import secure_filename

from storage.base import StorageError, StorageService


class LocalStorage(StorageService):
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as error:
            raise StorageError("Invalid storage key.") from error
        return candidate

    def save(
        self,
        stream: BinaryIO,
        *,
        original_name: str,
        namespace: str,
    ) -> str:
        safe_namespace = secure_filename(namespace) or "general"
        safe_name = secure_filename(original_name) or "file"
        key = f"{safe_namespace}/{uuid4().hex}_{safe_name}"
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("wb") as output:
                shutil.copyfileobj(stream, output)
        except OSError as error:
            raise StorageError("The file could not be stored.") from error
        return key

    def open(self, key: str, mode: str = "rb"):
        try:
            return self._resolve(key).open(mode)
        except OSError as error:
            raise StorageError("The stored file could not be opened.") from error

    def delete(self, key: str) -> None:
        try:
            self._resolve(key).unlink(missing_ok=True)
        except OSError as error:
            raise StorageError("The stored file could not be deleted.") from error

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def path_for(self, key: str) -> Path | None:
        return self._resolve(key)
