"""Security and request-hardening helpers for LifeOS."""

from __future__ import annotations

import re
import secrets
from urllib.parse import urlsplit

from flask import abort, current_app, g, request


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


def _request_id() -> str:
    """Accept only log-safe client correlation IDs; otherwise create our own."""

    supplied = (request.headers.get("X-Request-ID") or "").strip()
    if supplied and _REQUEST_ID_RE.fullmatch(supplied):
        return supplied
    return secrets.token_hex(12)


def _configured_allowed_hosts() -> set[str]:
    hosts = {
        str(item or "").strip().casefold().rstrip(".")
        for item in (current_app.config.get("ALLOWED_HOSTS") or ())
        if str(item or "").strip()
    }

    # PUBLIC_BASE_URL is already required to be HTTPS in production and is a
    # useful canonical-host source even when ALLOWED_HOSTS is left empty.
    public_base_url = str(current_app.config.get("PUBLIC_BASE_URL") or "").strip()
    if current_app.config.get("ENV_NAME") == "production" and public_base_url:
        parsed = urlsplit(public_base_url)
        if parsed.hostname:
            hosts.add(parsed.hostname.casefold().rstrip("."))
    return hosts


def _host_is_allowed() -> bool:
    allowed = _configured_allowed_hosts()
    if not allowed:
        # Development/test environments may intentionally have no fixed host.
        return current_app.config.get("ENV_NAME") != "production"

    hostname = str(request.hostname or "").casefold().rstrip(".")
    return bool(hostname and hostname in allowed)


def _effective_port(*, scheme: str, explicit_port: int | None) -> int | None:
    if explicit_port is not None:
        return explicit_port
    if scheme == "https":
        return 443
    if scheme == "http":
        return 80
    return None


def _request_origin_is_same_origin(origin: str) -> bool:
    """Require the browser Origin to match scheme, host, and effective port.

    Same-*host* is not enough: ``http://lifeos.example`` and
    ``https://lifeos.example`` are different origins, as are two different ports.
    ProxyFix, when explicitly enabled behind a trusted proxy, normalises the request
    scheme/host before this check runs.
    """

    try:
        parsed = urlsplit(origin)
        request_host = urlsplit(f"//{request.host}")
    except ValueError:
        return False

    scheme = str(parsed.scheme or "").casefold()
    request_scheme = str(request.scheme or "").casefold()
    if scheme not in {"http", "https"} or request_scheme not in {"http", "https"}:
        return False
    if not parsed.hostname or not request_host.hostname:
        return False

    origin_host = parsed.hostname.casefold().rstrip(".")
    current_host = request_host.hostname.casefold().rstrip(".")
    if origin_host != current_host or scheme != request_scheme:
        return False

    try:
        origin_port = _effective_port(scheme=scheme, explicit_port=parsed.port)
        current_port = _effective_port(scheme=request_scheme, explicit_port=request_host.port)
    except ValueError:
        return False
    return origin_port == current_port


def _normalize_origin(origin: str) -> str | None:
    """Return a canonical exact origin or None for malformed/non-origin input."""

    try:
        parsed = urlsplit(str(origin or "").strip())
    except ValueError:
        return None

    scheme = str(parsed.scheme or "").casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return None

    hostname = parsed.hostname.casefold().rstrip(".")
    try:
        port = _effective_port(scheme=scheme, explicit_port=parsed.port)
    except ValueError:
        return None

    default_port = 443 if scheme == "https" else 80
    if port == default_port:
        return f"{scheme}://{hostname}"
    return f"{scheme}://{hostname}:{port}"


def _configured_trusted_api_origins() -> set[str]:
    trusted: set[str] = set()
    for value in current_app.config.get("TRUSTED_API_ORIGINS") or ():
        normalized = _normalize_origin(str(value or ""))
        if normalized:
            trusted.add(normalized)
    return trusted


def _request_origin_is_allowed(origin: str) -> bool:
    """Allow the Flask origin or an explicitly configured proxy-preserved origin.

    This is intentionally not a CORS switch. Sec-Fetch-Site cross-site requests are
    still rejected before this check and Flask-WTF CSRF remains mandatory. The
    allowlist exists for same-origin browser requests forwarded through Vite or a
    trusted reverse proxy whose upstream Host differs from the browser Origin.
    """

    if _request_origin_is_same_origin(origin):
        return True
    normalized = _normalize_origin(origin)
    return bool(normalized and normalized in _configured_trusted_api_origins())


def _enforce_api_request_boundary() -> None:
    """Defense-in-depth around the cookie-authenticated React API.

    Flask-WTF CSRF remains the primary CSRF boundary.  Origin/Fetch-Metadata
    checks below make cross-site unsafe requests fail even earlier, and the JSON
    size guard prevents a normal API endpoint from inheriting the much larger PDF
    upload allowance.
    """

    if not request.path.startswith("/api/") or request.method in SAFE_METHODS:
        return

    fetch_site = (request.headers.get("Sec-Fetch-Site") or "").strip().casefold()
    if fetch_site == "cross-site":
        abort(403)

    origin = (request.headers.get("Origin") or "").strip()
    if origin and (origin == "null" or not _request_origin_is_allowed(origin)):
        abort(403)

    if request.mimetype == "application/json":
        content_length = request.content_length
        max_json_bytes = int(current_app.config.get("MAX_API_JSON_BYTES") or 0)
        if max_json_bytes > 0 and content_length is not None and content_length > max_json_bytes:
            abort(413)


def init_security(app) -> None:
    """Register request validation, identifiers, and conservative headers.

    LifeOS deliberately uses a partial CSP here.  It protects framing, base URLs,
    and form destinations without breaking the remaining legacy inline script/style
    compatibility surface.  A strict script/style CSP can be added once that legacy
    surface is fully removed.
    """

    @app.before_request
    def apply_request_security() -> None:
        g.request_id = _request_id()
        if request.method == "TRACE":
            abort(405)
        if not _host_is_allowed():
            abort(403)
        _enforce_api_request_boundary()

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        response.headers.setdefault(
            "Referrer-Policy",
            "strict-origin-when-cross-origin",
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        response.headers.setdefault("X-Request-ID", g.get("request_id", ""))

        # Avoid storing private workspace pages/API payloads in shared browser
        # caches or search indexes.
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
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
            response.vary.add("Cookie")

        if current_app.config.get("ENV_NAME") == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response
