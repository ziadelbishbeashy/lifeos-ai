"""Gemini provider adapter with lazy SDK imports and exact usage capture."""

from __future__ import annotations

from typing import Any

from ai.providers.base import (
    AIProvider,
    ProviderGeneration,
    ProviderRequestError,
    ProviderUsage,
    ProviderWebGeneration,
    ProviderWebSource,
)


def _usage_value(usage: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        if value is None:
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return None


def _extract_usage(response: Any) -> ProviderUsage:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return ProviderUsage()

    input_tokens = _usage_value(usage, "prompt_token_count", "promptTokenCount")
    output_tokens = _usage_value(usage, "candidates_token_count", "candidatesTokenCount")
    thinking_tokens = _usage_value(usage, "thoughts_token_count", "thoughtsTokenCount")
    cached_tokens = _usage_value(
        usage,
        "cached_content_token_count",
        "cachedContentTokenCount",
    )
    total_tokens = _usage_value(usage, "total_token_count", "totalTokenCount")

    raw = {
        "prompt_token_count": input_tokens,
        "candidates_token_count": output_tokens,
        "thoughts_token_count": thinking_tokens,
        "cached_content_token_count": cached_tokens,
        "total_token_count": total_tokens,
    }
    return ProviderUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        cached_input_tokens=cached_tokens,
        total_tokens=total_tokens,
        raw=raw,
    )


class GeminiProvider(AIProvider):
    provider_name = "gemini"

    def generate_text(self, *, model: str, prompt: str) -> ProviderGeneration:
        try:
            from google import genai

            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            return ProviderGeneration(
                text=(response.text or "").strip(),
                usage=_extract_usage(response),
            )
        except Exception as error:
            raise ProviderRequestError(str(error)) from error

    def generate_json_text(self, *, model: str, prompt: str) -> ProviderGeneration:
        """Generate syntactically valid JSON using Gemini's native JSON mode."""

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            return ProviderGeneration(
                text=(response.text or "").strip(),
                usage=_extract_usage(response),
            )
        except Exception as error:
            raise ProviderRequestError(str(error)) from error

    def generate_web_research(self, *, model: str, prompt: str) -> ProviderWebGeneration:
        """Use Gemini's hosted Google Search grounding in read-only mode."""

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )

            sources: list[ProviderWebSource] = []
            search_queries: list[str] = []
            candidates = list(getattr(response, "candidates", None) or [])
            metadata = getattr(candidates[0], "grounding_metadata", None) if candidates else None
            if metadata is not None:
                for raw_query in list(getattr(metadata, "web_search_queries", None) or []):
                    query = " ".join(str(raw_query or "").split()).strip()
                    if query and query not in search_queries:
                        search_queries.append(query[:500])

                seen_urls: set[str] = set()
                for chunk in list(getattr(metadata, "grounding_chunks", None) or []):
                    web = getattr(chunk, "web", None)
                    if web is None:
                        continue
                    url = " ".join(str(getattr(web, "uri", "") or "").split()).strip()
                    title = " ".join(str(getattr(web, "title", "") or "").split()).strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    sources.append(ProviderWebSource(title=title or url, url=url))

            return ProviderWebGeneration(
                text=(response.text or "").strip(),
                sources=tuple(sources),
                search_queries=tuple(search_queries),
                usage=_extract_usage(response),
            )
        except Exception as error:
            raise ProviderRequestError(str(error)) from error

