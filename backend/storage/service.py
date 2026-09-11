"""Resolve the configured LifeOS storage backend."""

from __future__ import annotations

from flask import current_app

from storage.base import StorageError, StorageService
from storage.local import LocalStorage


def get_storage() -> StorageService:
    backend = str(current_app.config.get("STORAGE_BACKEND", "local")).lower()
    if backend == "local":
        return LocalStorage(current_app.config["LOCAL_STORAGE_ROOT"])
    raise StorageError(
        f'Unsupported storage backend "{backend}". '
        "Use local until the Azure Blob adapter is enabled."
    )
