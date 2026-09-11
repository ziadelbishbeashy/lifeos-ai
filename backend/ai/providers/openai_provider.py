"""OpenAI provider adapter with lazy SDK imports and usage capture when available."""

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


def _value(obj: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(obj, name, None)
        if value is None and isinstance(obj, dict):
            value = obj.get(name)
        if value is None:
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return None




def _openai_usage(response: Any) -> ProviderUsage:
    usage = getattr(response, "usage", None)
    input_tokens = _value(usage, "input_tokens") if usage is not None else None
    output_tokens = _value(usage, "output_tokens") if usage is not None else None
    total_tokens = _value(usage, "total_tokens") if usage is not None else None

    cached_tokens = None
    input_details = getattr(usage, "input_tokens_details", None) if usage is not None else None
    if input_details is not None:
        cached_tokens = _value(input_details, "cached_tokens")

    reasoning_tokens = None
    output_details = getattr(usage, "output_tokens_details", None) if usage is not None else None
    if output_details is not None:
        reasoning_tokens = _value(output_details, "reasoning_tokens")

    visible_output_tokens = output_tokens
    if output_tokens is not None and reasoning_tokens is not None:
        visible_output_tokens = max(0, output_tokens - reasoning_tokens)

    return ProviderUsage(
        input_tokens=input_tokens,
        output_tokens=visible_output_tokens,
        thinking_tokens=reasoning_tokens,
        cached_input_tokens=cached_tokens,
        total_tokens=total_tokens,
    )


def _source_value(obj: Any, name: str) -> Any:
    value = getattr(obj, name, None)
    if value is None and isinstance(obj, dict):
        value = obj.get(name)
    return value


def _openai_web_sources(response: Any) -> tuple[ProviderWebSource, ...]:
    sources: list[ProviderWebSource] = []
    seen: set[str] = set()

    def add(raw: Any) -> None:
        url = " ".join(str(_source_value(raw, "url") or "").split()).strip()
        title = " ".join(str(_source_value(raw, "title") or "").split()).strip()
        if not url or url in seen:
            return
        seen.add(url)
        sources.append(ProviderWebSource(title=title or url, url=url))

    for item in list(getattr(response, "output", None) or []):
        item_type = str(_source_value(item, "type") or "")
        if item_type == "message":
            for content in list(_source_value(item, "content") or []):
                for annotation in list(_source_value(content, "annotations") or []):
                    if str(_source_value(annotation, "type") or "") == "url_citation":
                        add(annotation)
        elif item_type == "web_search_call":
            action = _source_value(item, "action")
            for source in list(_source_value(action, "sources") or []):
                add(source)
    return tuple(sources)


class OpenAIProvider(AIProvider):
    provider_name = "openai"

    def generate_text(self, *, model: str, prompt: str) -> ProviderGeneration:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.responses.create(model=model, input=prompt)
            return ProviderGeneration(
                text=(response.output_text or "").strip(),
                usage=_openai_usage(response),
            )
        except Exception as error:
            raise ProviderRequestError(str(error)) from error

    def generate_json_text(self, *, model: str, prompt: str) -> ProviderGeneration:
        """Generate valid JSON using Responses API JSON mode."""

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.responses.create(
                model=model,
                input=prompt,
                text={"format": {"type": "json_object"}},
            )
            return ProviderGeneration(
                text=(response.output_text or "").strip(),
                usage=_openai_usage(response),
            )
        except Exception as error:
            raise ProviderRequestError(str(error)) from error

    def generate_web_research(self, *, model: str, prompt: str) -> ProviderWebGeneration:
        """Use the hosted Responses API web_search tool in read-only mode."""

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.responses.create(
                model=model,
                tools=[{"type": "web_search"}],
                tool_choice="required",
                include=["web_search_call.action.sources"],
                input=prompt,
            )
            return ProviderWebGeneration(
                text=(response.output_text or "").strip(),
                sources=_openai_web_sources(response),
                usage=_openai_usage(response),
            )
        except Exception as error:
            raise ProviderRequestError(str(error)) from error

