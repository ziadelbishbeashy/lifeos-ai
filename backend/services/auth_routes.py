"""Backward-compatible import for the former authentication module.

New code must import ``auth_bp`` from ``routes.auth_routes``.  This shim keeps
older local imports from breaking while the project is refactored gradually.
"""

from routes.auth_routes import auth_bp

__all__ = ["auth_bp"]
