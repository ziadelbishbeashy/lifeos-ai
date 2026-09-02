"""LifeOS application package.

Foundation V2 introduces a stable package boundary without rewriting the
existing business logic in one risky migration. Importing a low-level module
such as ``lifeos.core.database`` must not boot the Flask application, because
standalone tooling (notably Alembic) imports those modules before an app
context exists.
"""

from __future__ import annotations

from typing import Any


def create_app(*args: Any, **kwargs: Any):
    """Lazily import the application factory.

    Keeping this import lazy prevents ``import lifeos.core.database`` from
    recursively importing API routes/models while the compatibility
    ``database`` module is still being initialized.
    """

    from lifeos.application import create_app as _create_app

    return _create_app(*args, **kwargs)


__all__ = ["create_app"]
