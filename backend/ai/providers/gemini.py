"""Gemini provider adapter with lazy SDK imports."""

from __future__ import annotations

from ai.providers.base import AIProvider, ProviderRequestError


class GeminiProvider(AIProvider):
    provider_name = "gemini"

    def generate_text(self, *, model: str, prompt: str) -> str:
        try:
            from google import genai

            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            return (response.text or "").strip()
        except Exception as error:
            raise ProviderRequestError(str(error)) from error
