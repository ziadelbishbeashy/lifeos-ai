"""Storage contracts for LifeOS documents and generated files."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


class StorageError(RuntimeError):
    """Raised when a storage operation cannot be completed safely."""


class StorageService(ABC):
    @abstractmethod
    def save(
        self,
        stream: BinaryIO,
        *,
        original_name: str,
        namespace: str,
    ) -> str:
        """Persist a stream and return a provider-independent storage key."""

    @abstractmethod
    def open(self, key: str, mode: str = "rb"):
        """Open a stored object."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a stored object when it exists."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether a stored object exists."""

    @abstractmethod
    def path_for(self, key: str) -> Path | None:
        """Return a local path when supported, otherwise None."""
