"""LifeOS application package.

Foundation V2 introduces a stable package boundary without rewriting the
existing business logic in one risky migration. New code should import from
``lifeos`` packages; legacy modules remain available during the transition.
"""

from lifeos.application import create_app

__all__ = ["create_app"]
