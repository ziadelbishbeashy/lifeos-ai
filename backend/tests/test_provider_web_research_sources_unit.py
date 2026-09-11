from types import SimpleNamespace

from ai.providers.openai_provider import _openai_web_sources


def test_openai_web_sources_normalize_message_citations_and_search_sources():
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(annotations=[
                    SimpleNamespace(type="url_citation", title="Official docs", url="https://example.com/docs"),
                ])],
            ),
            SimpleNamespace(
                type="web_search_call",
                action=SimpleNamespace(sources=[
                    {"type": "url", "title": "Pricing", "url": "https://example.com/pricing"},
                    {"type": "url", "title": "Duplicate", "url": "https://example.com/docs"},
                ]),
            ),
        ]
    )

    sources = _openai_web_sources(response)
    assert [(source.title, source.url) for source in sources] == [
        ("Official docs", "https://example.com/docs"),
        ("Pricing", "https://example.com/pricing"),
    ]
