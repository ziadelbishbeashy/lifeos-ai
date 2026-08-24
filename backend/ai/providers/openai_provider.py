"""OpenAI provider adapter with lazy SDK imports."""

from __future__ import annotations

from ai.providers.base import AIProvider, ProviderRequestError


class OpenAIProvider(AIProvider):
    provider_name = "openai"

    def generate_text(self, *, model: str, prompt: str) -> str:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.responses.create(model=model, input=prompt)
            return (response.output_text or "").strip()
        except Exception as error:
            raise ProviderRequestError(str(error)) from error
