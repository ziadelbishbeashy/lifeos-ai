"""LifeOS storage package."""

from storage.base import StorageError, StorageService
from storage.service import get_storage

__all__ = ["StorageError", "StorageService", "get_storage"]
