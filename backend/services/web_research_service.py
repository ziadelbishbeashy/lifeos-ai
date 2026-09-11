"""Read-only public web research for Ask LifeOS.

LifeOS delegates search to provider-hosted web search tools. This service never
opens an interactive browser, logs in to websites, submits forms, or exposes
workspace credentials. The only output is public text + attributable URLs.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os
import re
from typing import Any
from urllib.parse import urlparse

from ai.provider_router import (
    AIProviderRouterError,
    generate_web_research as route_web_research,
)
from services.ai_service import AIServiceError, get_ai_configuration


MAX_WEB_QUERY_CHARACTERS = 420
MAX_WEB_SUMMARY_CHARACTERS = 12_000
DEFAULT_MAX_WEB_SOURCES = 6
MAX_WEB_SOURCES = 10


class WebResearchError(RuntimeError):
    """Base public-web research error."""


class WebResearchDisabledError(WebResearchError):
    """Raised when web research is disabled by deployment policy."""


class WebResearchPrivacyError(WebResearchError):
    """Raised when a query looks like it contains a credential/secret."""


@dataclass(frozen=True)
class WebSource:
    source_id: str
    title: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.source_id,
            "title": self.title,
            "url": self.url,
        }


@dataclass(frozen=True)
class WebResearchResult:
    query: str
    summary: str
    sources: tuple[WebSource, ...]
    provider_queries: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "summary": self.summary,
            "sources": [item.to_dict() for item in self.sources],
            "source_count": len(self.sources),
            "read_only": True,
            "provider_hosted_search": True,
        }

    @property
    def source_ids(self) -> frozenset[str]:
        return frozenset(item.source_id for item in self.sources)


_SECRET_PATTERNS = (
    re.compile(r"\b(?:postgres(?:ql)?|mysql|mssql|mongodb(?:\+srv)?)://", re.I),
    re.compile(r"\b(?:password|passwd|pwd|api[_ -]?key|secret|access[_ -]?token|bearer)\s*[:=]", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(
        r"\b(?:database_url|db_url|openai_api_key|gemini_api_key|secret_key|jwt_secret|"
        r"client_secret|private_key|refresh_token)\s*[:=]\s*\S+",
        re.I,
    ),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I),
)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _max_sources() -> int:
    try:
        value = int(os.getenv("ASK_LIFEOS_WEB_MAX_SOURCES") or DEFAULT_MAX_WEB_SOURCES)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_WEB_SOURCES
    return max(1, min(MAX_WEB_SOURCES, value))


def _contains_secret(value: str) -> bool:
    text = str(value or "")
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _remove_private_context_label(
    query: str,
    *,
    original_query: str,
    selected_context_label: str | None,
) -> str:
    label = " ".join(str(selected_context_label or "").split()).strip()
    if not label:
        return query
    # If the user explicitly typed the label, it is their choice to make that
    # public research term. The request-understanding model is not allowed to
    # leak a label that came only from the selected LifeOS context chip.
    if label.casefold() in str(original_query or "").casefold():
        return query
    return re.sub(re.escape(label), " ", query, flags=re.IGNORECASE)


def sanitize_public_web_query(
    *,
    proposed_query: str,
    original_query: str,
    selected_context_label: str | None = None,
) -> str:
    """Create a bounded public query without auto-leaking selected context."""

    if _contains_secret(original_query) or _contains_secret(proposed_query):
        raise WebResearchPrivacyError(
            "Web research was skipped because the request appears to contain a credential or secret."
        )

    query = " ".join(str(proposed_query or original_query or "").split()).strip()
    query = _remove_private_context_label(
        query,
        original_query=original_query,
        selected_context_label=selected_context_label,
    )
    query = " ".join(query.split()).strip(" -:;,.")
    if not query:
        # Fall back to the user's public wording, still without silently adding
        # selected LifeOS context.
        query = " ".join(str(original_query or "").split()).strip()
    if not query:
        raise WebResearchError("A public research query is required.")
    if len(query) > MAX_WEB_QUERY_CHARACTERS:
        query = query[:MAX_WEB_QUERY_CHARACTERS].rstrip()
    if _contains_secret(query):
        raise WebResearchPrivacyError(
            "Web research was skipped because the public query appears to contain a credential or secret."
        )
    return query


def _safe_public_url(raw: str) -> str | None:
    value = " ".join(str(raw or "").split()).strip()
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    # Credentials in public source URLs are never reflected into the UI.
    if parsed.username or parsed.password:
        return None
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname or hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        return None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        # Provider-hosted public search must never surface loopback/private/link-
        # local/reserved addresses as clickable "web sources" in the product UI.
        return None
    return value[:2_000]


def research_public_web(
    *,
    query: str,
    original_query: str,
    selected_context_label: str | None = None,
) -> WebResearchResult:
    """Run one bounded, read-only provider-hosted public web search."""

    if not _bool_env("ASK_LIFEOS_WEB_RESEARCH_ENABLED", True):
        raise WebResearchDisabledError("Ask LifeOS web research is disabled.")

    public_query = sanitize_public_web_query(
        proposed_query=query,
        original_query=original_query,
        selected_context_label=selected_context_label,
    )

    try:
        config = get_ai_configuration()
    except AIServiceError as error:
        raise WebResearchError(str(error)) from error

    prompt = f"""
You are the read-only public web research tool inside LifeOS.
Research ONLY the public query below using the provider's hosted web search.
Do not attempt logins, purchases, form submissions, account changes, downloads,
or any other website action.

PRIVACY RULES:
- You have no access to private LifeOS workspace state in this call.
- Do not guess private project names, user data, database values, credentials, or hidden configuration.
- Treat the query only as a public research query.

OUTPUT GOAL:
Return a concise factual research brief useful to a separate LifeOS reasoner.
Prioritize primary/official sources for technical documentation, prices, releases,
security advisories, laws/rules, and product capabilities when available.
Do not fabricate sources. The provider will return source metadata separately.

PUBLIC QUERY:
{public_query}
""".strip()

    try:
        generation = route_web_research(
            provider=config["provider"],
            api_key=config["api_key"],
            model=config["model"],
            feature="ask_lifeos_web_research",
            prompt=prompt,
            empty_message="Web research returned no usable public information.",
        )
    except AIProviderRouterError as error:
        raise WebResearchError(str(error)) from error

    sources: list[WebSource] = []
    seen: set[str] = set()
    for raw in generation.sources:
        url = _safe_public_url(raw.url)
        if not url or url in seen:
            continue
        seen.add(url)
        title = " ".join(str(raw.title or "").split()).strip() or url
        sources.append(
            WebSource(
                source_id=f"W{len(sources) + 1}",
                title=title[:500],
                url=url,
            )
        )
        if len(sources) >= _max_sources():
            break

    summary = str(generation.text or "").strip()
    if len(summary) > MAX_WEB_SUMMARY_CHARACTERS:
        summary = summary[:MAX_WEB_SUMMARY_CHARACTERS].rstrip() + "…"
    if not summary:
        raise WebResearchError("Web research returned no usable public information.")
    if not sources:
        # Public-web prose without attributable URLs is not evidence. Fail
        # closed so the downstream reasoner cannot present uncited current
        # information as researched fact.
        raise WebResearchError("Web research returned no attributable public sources.")

    return WebResearchResult(
        query=public_query,
        summary=summary,
        sources=tuple(sources),
        provider_queries=tuple(generation.search_queries[:8]),
    )
