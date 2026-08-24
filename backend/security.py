"""Security and request-hardening helpers for LifeOS."""

from __future__ import annotations

import secrets
from datetime import timedelta

from flask import current_app, g, request


SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _request_id() -> str:
    supplied = (request.headers.get("X-Request-ID") or "").strip()
    if supplied and len(supplied) <= 100:
        return supplied
    return secrets.token_hex(12)


def init_security(app) -> None:
    """Register request identifiers and conservative response headers.

    A strict Content-Security-Policy is intentionally deferred because the
    current templates still contain inline scripts and styles. Enabling a
    strict policy before those are extracted would break the working UI.
    """

    @app.before_request
    def attach_request_id() -> None:
        g.request_id = _request_id()

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy",
            "strict-origin-when-cross-origin",
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), payment=(), usb=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("X-Request-ID", g.get("request_id", ""))

        # Avoid storing private workspace pages in shared browser caches.
        if request.path.startswith(
            (
                "/api/",
                "/dashboard",
                "/projects",
                "/tasks",
                "/notes",
                "/focus",
                "/analytics",
                "/notifications",
            )
        ):
            response.headers.setdefault(
                "Cache-Control",
                "no-store, max-age=0",
            )
            response.headers.setdefault("Pragma", "no-cache")

        if current_app.config.get("ENV_NAME") == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response
