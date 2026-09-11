"""Stable ownership-safe public interface for Document Brain."""
from services.document_access_service import (
    DocumentNotFoundError,
    DocumentPersistenceError,
    DocumentValidationError,
    list_owned_documents,
    require_owned_document,
)
__all__ = [name for name in globals() if not name.startswith("_")]
