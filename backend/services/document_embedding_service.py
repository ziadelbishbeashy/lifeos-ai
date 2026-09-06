"""Persistent embeddings for LifeOS document chunks."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime

from google import genai
from google.genai import types
from sqlalchemy.exc import SQLAlchemyError

from ai.providers.base import ProviderUsage
from database import db
from models import Document, DocumentChunk
from services.ai_pricing_service import calculate_usage_cost
from services.ai_usage_service import record_embedding_usage
from services.resource_limit_service import (
    ResourceLimitError,
    get_resource_limits,
    guard_embedding_request,
)
from services.document_chunk_service import (
    DocumentChunkError,
    DocumentChunkNotFoundError,
    DocumentChunkNotReadyError,
    ensure_owned_document_chunks,
)


DEFAULT_EMBEDDING_MODEL = "gemini-embedding-2"
DEFAULT_EMBEDDING_DIMENSIONS = 768
DEFAULT_BATCH_SIZE = 20
MAX_EMBEDDING_DIMENSIONS = 3_072

EMBEDDING_PROVIDER = "gemini"
EMBEDDING_FORMAT_VERSION = "document-chunk-embedding-v1"


class DocumentEmbeddingError(RuntimeError):
    """Base error for document embedding operations."""


class DocumentEmbeddingConfigurationError(
    DocumentEmbeddingError
):
    """Raised when embedding configuration is invalid."""


class DocumentEmbeddingNotFoundError(
    DocumentEmbeddingError
):
    """Raised when a document is missing or not owned."""


class DocumentEmbeddingNotReadyError(
    DocumentEmbeddingError
):
    """Raised when a document cannot be embedded."""


@dataclass(frozen=True)
class EmbeddingConfiguration:
    """Validated Gemini embedding configuration."""

    provider: str
    api_key: str
    model: str
    dimensions: int


@dataclass(frozen=True)
class EmbeddedDocumentChunks:
    """Result of ensuring embeddings for one document."""

    document: Document
    chunks: list[DocumentChunk]
    embedded_count: int
    reused_count: int
    chunks_rebuilt: bool
    provider: str
    model: str
    dimensions: int


def get_embedding_configuration() -> EmbeddingConfiguration:
    """Read and validate embedding settings."""

    api_key = os.getenv(
        "GEMINI_API_KEY",
        "",
    ).strip()

    model = os.getenv(
        "GEMINI_EMBEDDING_MODEL",
        DEFAULT_EMBEDDING_MODEL,
    ).strip()

    raw_dimensions = os.getenv(
        "EMBEDDING_DIMENSIONS",
        str(DEFAULT_EMBEDDING_DIMENSIONS),
    ).strip()

    if not api_key:
        raise DocumentEmbeddingConfigurationError(
            "GEMINI_API_KEY was not found in the environment."
        )

    if not model:
        raise DocumentEmbeddingConfigurationError(
            "GEMINI_EMBEDDING_MODEL was not configured."
        )

    try:
        dimensions = int(
            raw_dimensions
        )

    except ValueError as error:
        raise DocumentEmbeddingConfigurationError(
            "EMBEDDING_DIMENSIONS must be a whole number."
        ) from error

    if dimensions < 1:
        raise DocumentEmbeddingConfigurationError(
            "EMBEDDING_DIMENSIONS must be greater than zero."
        )

    if dimensions > MAX_EMBEDDING_DIMENSIONS:
        raise DocumentEmbeddingConfigurationError(
            "EMBEDDING_DIMENSIONS cannot exceed "
            f"{MAX_EMBEDDING_DIMENSIONS:,}."
        )

    return EmbeddingConfiguration(
        provider=EMBEDDING_PROVIDER,
        api_key=api_key,
        model=model,
        dimensions=dimensions,
    )


def ensure_owned_document_embeddings(
    *,
    document_id: int,
    user_id: int,
    force: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> EmbeddedDocumentChunks:
    """
    Ensure every current chunk has a valid embedding.

    Existing embeddings are reused when the text, provider,
    model, dimensions and preparation format have not changed.
    """

    configuration = get_embedding_configuration()

    cleaned_batch_size = _validate_batch_size(
        batch_size
    )

    try:
        indexed_document = ensure_owned_document_chunks(
            document_id=document_id,
            user_id=user_id,
        )

    except DocumentChunkNotFoundError as error:
        raise DocumentEmbeddingNotFoundError(
            str(error)
        ) from error

    except DocumentChunkNotReadyError as error:
        raise DocumentEmbeddingNotReadyError(
            str(error)
        ) from error

    except DocumentChunkError as error:
        raise DocumentEmbeddingError(
            "LifeOS could not prepare the document chunks."
        ) from error

    chunks_to_embed: list[DocumentChunk] = []
    reused_count = 0

    for chunk in indexed_document.chunks:
        expected_fingerprint = create_embedding_fingerprint(
            chunk=chunk,
            configuration=configuration,
        )

        embedding_is_current = (
            chunk.has_embedding
            and chunk.embedding_provider
            == configuration.provider
            and chunk.embedding_model
            == configuration.model
            and chunk.embedding_dimensions
            == configuration.dimensions
            and chunk.embedding_fingerprint
            == expected_fingerprint
        )

        if embedding_is_current and not force:
            reused_count += 1
            continue

        chunks_to_embed.append(
            chunk
        )

    if not chunks_to_embed:
        return EmbeddedDocumentChunks(
            document=indexed_document.document,
            chunks=indexed_document.chunks,
            embedded_count=0,
            reused_count=reused_count,
            chunks_rebuilt=indexed_document.rebuilt,
            provider=configuration.provider,
            model=configuration.model,
            dimensions=configuration.dimensions,
        )

    client = genai.Client(
        api_key=configuration.api_key
    )

    try:
        for batch in _split_batches(
            chunks_to_embed,
            batch_size=cleaned_batch_size,
        ):
            prepared_texts = [
                prepare_document_chunk_for_embedding(
                    chunk
                )
                for chunk in batch
            ]

            vectors = _generate_embeddings(
                client=client,
                model=configuration.model,
                dimensions=configuration.dimensions,
                texts=prepared_texts,
                usage_user_id=user_id,
                usage_feature="document_chunk_embedding",
            )

            if len(vectors) != len(batch):
                raise DocumentEmbeddingError(
                    "The embedding provider returned an "
                    "unexpected number of vectors."
                )

            for chunk, vector in zip(
                batch,
                vectors,
            ):
                normalized_vector = normalize_vector(
                    vector
                )

                if (
                    len(normalized_vector)
                    != configuration.dimensions
                ):
                    raise DocumentEmbeddingError(
                        "The embedding provider returned a vector "
                        "with unexpected dimensions."
                    )

                chunk.embedding_json = json.dumps(
                    normalized_vector,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )

                chunk.embedding_provider = (
                    configuration.provider
                )

                chunk.embedding_model = (
                    configuration.model
                )

                chunk.embedding_dimensions = (
                    configuration.dimensions
                )

                chunk.embedding_fingerprint = (
                    create_embedding_fingerprint(
                        chunk=chunk,
                        configuration=configuration,
                    )
                )

                chunk.embedded_at = datetime.utcnow()

        db.session.commit()

    except DocumentEmbeddingError:
        db.session.rollback()
        raise

    except SQLAlchemyError as error:
        db.session.rollback()

        raise DocumentEmbeddingError(
            "LifeOS generated the embeddings but could not "
            "save them."
        ) from error

    except Exception as error:
        db.session.rollback()

        raise DocumentEmbeddingError(
            "The embedding provider could not process "
            "the document chunks."
        ) from error

    return EmbeddedDocumentChunks(
        document=indexed_document.document,
        chunks=indexed_document.chunks,
        embedded_count=len(chunks_to_embed),
        reused_count=reused_count,
        chunks_rebuilt=indexed_document.rebuilt,
        provider=configuration.provider,
        model=configuration.model,
        dimensions=configuration.dimensions,
    )


def prepare_document_chunk_for_embedding(
    chunk: DocumentChunk,
) -> str:
    """
    Prepare one stored chunk for semantic retrieval.

    The instruction tells the embedding model that this text
    represents searchable document knowledge.
    """

    section_title = str(
        chunk.section_title or ""
    ).strip()

    page_label = _page_label(
        chunk
    )

    return (
        "Task: Represent this LifeOS document passage for "
        "retrieval in a question-answering system.\n"
        f"Document page: {page_label}\n"
        f"Section title: {section_title or 'Unknown'}\n"
        "Passage:\n"
        f"{str(chunk.text or '').strip()}"
    )


def prepare_question_for_embedding(
    question: str,
) -> str:
    """Prepare a user question for semantic retrieval."""

    cleaned_question = " ".join(
        str(question or "").split()
    ).strip()

    if not cleaned_question:
        raise DocumentEmbeddingError(
            "Enter a question before creating its embedding."
        )

    return (
        "Task: Retrieve LifeOS document passages that answer "
        "the following question.\n"
        f"Question: {cleaned_question}"
    )


def create_embedding_fingerprint(
    *,
    chunk: DocumentChunk,
    configuration: EmbeddingConfiguration,
) -> str:
    """
    Identify the exact text and settings used for an embedding.

    A change to the text, model, dimensions or preparation
    format causes a new fingerprint.
    """

    fingerprint_input = "\n".join(
        [
            EMBEDDING_FORMAT_VERSION,
            configuration.provider,
            configuration.model,
            str(configuration.dimensions),
            str(chunk.source_fingerprint or ""),
            prepare_document_chunk_for_embedding(
                chunk
            ),
        ]
    )

    return hashlib.sha256(
        fingerprint_input.encode(
            "utf-8"
        )
    ).hexdigest()


def normalize_vector(
    vector: list[float],
) -> list[float]:
    """Normalize a vector to unit length."""

    try:
        values = [
            float(value)
            for value in vector
        ]

    except (
        TypeError,
        ValueError,
    ) as error:
        raise DocumentEmbeddingError(
            "The embedding contained invalid values."
        ) from error

    magnitude = math.sqrt(
        sum(
            value * value
            for value in values
        )
    )

    if magnitude == 0:
        raise DocumentEmbeddingError(
            "The embedding provider returned a zero vector."
        )

    return [
        value / magnitude
        for value in values
    ]


def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    """
    Calculate cosine similarity for normalized or raw vectors.

    Values closer to 1 indicate stronger semantic similarity.
    """

    if len(vector_a) != len(vector_b):
        raise DocumentEmbeddingError(
            "Embedding vectors must use the same dimensions."
        )

    normalized_a = normalize_vector(
        vector_a
    )

    normalized_b = normalize_vector(
        vector_b
    )

    return sum(
        value_a * value_b
        for value_a, value_b in zip(
            normalized_a,
            normalized_b,
        )
    )


def _usage_value(value, *names: str) -> int | None:
    for name in names:
        raw = getattr(value, name, None)
        if raw is None and isinstance(value, dict):
            raw = value.get(name)
        if raw is None:
            continue
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            continue
    return None


def _embedding_input_tokens(
    *,
    client: genai.Client,
    model: str,
    contents,
    response,
) -> tuple[int | None, str]:
    """Return exact embedding input tokens when the SDK exposes them.

    Current embed responses do not consistently include generation-style
    ``usage_metadata``. When absent, Gemini's count_tokens endpoint is used on
    the exact request contents. A counting failure never breaks retrieval; the
    ledger simply leaves cost unknown instead of inventing a token estimate.
    """

    usage_metadata = getattr(response, "usage_metadata", None)
    if usage_metadata is not None:
        tokens = _usage_value(
            usage_metadata,
            "prompt_token_count",
            "promptTokenCount",
            "total_token_count",
            "totalTokenCount",
        )
        if tokens is not None:
            return tokens, "embed_response_usage"

    try:
        counted = client.models.count_tokens(
            model=model,
            contents=contents,
        )
        tokens = _usage_value(counted, "total_tokens", "totalTokens")
        if tokens is not None:
            return tokens, "count_tokens"
    except Exception:
        pass

    return None, "unavailable"


def _generate_embeddings(
    *,
    client: genai.Client,
    model: str,
    dimensions: int,
    texts: list[str],
    usage_user_id: int | None = None,
    usage_feature: str = "document_embedding",
) -> list[list[float]]:
    """
    Generate one separate vector for every supplied text.

    Gemini Embedding 2 aggregates a plain list of strings into
    one embedding. Each text must therefore be wrapped in its
    own Content object.
    """

    if not texts:
        return []

    try:
        provider_call_index = guard_embedding_request(
            provider=EMBEDDING_PROVIDER,
            model=model,
            texts=texts,
        )
    except ResourceLimitError as error:
        raise DocumentEmbeddingError(str(error)) from error

    separate_contents = [
        types.Content(
            parts=[
                types.Part.from_text(
                    text=text
                )
            ]
        )
        for text in texts
    ]

    started = time.perf_counter()
    prompt_characters = sum(len(str(text or "")) for text in texts)
    try:
        response = client.models.embed_content(
            model=model,
            contents=separate_contents,
            config=types.EmbedContentConfig(
                output_dimensionality=dimensions,
            ),
        )
    except Exception as error:
        latency_ms = round((time.perf_counter() - started) * 1000)
        usage = ProviderUsage()
        record_embedding_usage(
            provider=EMBEDDING_PROVIDER,
            model=model,
            feature=usage_feature,
            prompt_characters=prompt_characters,
            provider_call_index=provider_call_index,
            usage=usage,
            cost=calculate_usage_cost(provider=EMBEDDING_PROVIDER, model=model, usage=usage),
            latency_ms=latency_ms,
            success=False,
            error_category=type(error).__name__,
            user_id=usage_user_id,
        )
        raise

    prompt_tokens, token_count_source = _embedding_input_tokens(
        client=client,
        model=model,
        contents=separate_contents,
        response=response,
    )
    usage = ProviderUsage(
        input_tokens=prompt_tokens,
        total_tokens=prompt_tokens,
        raw={
            "prompt_token_count": prompt_tokens,
            "token_count_source": token_count_source,
        },
    )
    latency_ms = round((time.perf_counter() - started) * 1000)
    record_embedding_usage(
        provider=EMBEDDING_PROVIDER,
        model=model,
        feature=usage_feature,
        prompt_characters=prompt_characters,
        provider_call_index=provider_call_index,
        usage=usage,
        cost=calculate_usage_cost(provider=EMBEDDING_PROVIDER, model=model, usage=usage),
        latency_ms=latency_ms,
        success=True,
        user_id=usage_user_id,
    )

    embeddings = response.embeddings or []

    vectors: list[list[float]] = []

    for embedding in embeddings:
        values = embedding.values or []

        vectors.append(
            [
                float(value)
                for value in values
            ]
        )

    return vectors


def _split_batches(
    chunks: list[DocumentChunk],
    *,
    batch_size: int,
) -> list[list[DocumentChunk]]:
    """Split chunks into provider request batches."""

    return [
        chunks[index:index + batch_size]
        for index in range(
            0,
            len(chunks),
            batch_size,
        )
    ]


def _validate_batch_size(
    batch_size: int,
) -> int:
    try:
        cleaned_batch_size = int(
            batch_size
        )

    except (
        TypeError,
        ValueError,
    ) as error:
        raise DocumentEmbeddingError(
            "Embedding batch size must be a number."
        ) from error

    if cleaned_batch_size < 1:
        raise DocumentEmbeddingError(
            "Embedding batch size must be at least 1."
        )

    max_batch_size = get_resource_limits().max_embedding_batch_size
    if cleaned_batch_size > max_batch_size:
        raise DocumentEmbeddingError(
            f"Embedding batch size cannot exceed {max_batch_size}."
        )

    return cleaned_batch_size


def _page_label(
    chunk: DocumentChunk,
) -> str:
    if (
        chunk.page_start
        and chunk.page_end
        and chunk.page_start != chunk.page_end
    ):
        return (
            f"{chunk.page_start}-{chunk.page_end}"
        )

    if chunk.page_start:
        return str(
            chunk.page_start
        )

    if chunk.page_end:
        return str(
            chunk.page_end
        )

    return "Unknown"

def generate_question_embedding(
    *,
    question: str,
    configuration: EmbeddingConfiguration | None = None,
) -> tuple[
    list[float],
    EmbeddingConfiguration,
]:
    """
    Generate one normalized embedding for a user question.

    The same provider, model and dimensions used for document
    chunks must also be used for the question.
    """

    active_configuration = (
        configuration
        or get_embedding_configuration()
    )

    prepared_question = (
        prepare_question_for_embedding(
            question
        )
    )

    client = genai.Client(
        api_key=active_configuration.api_key
    )

    try:
        vectors = _generate_embeddings(
            client=client,
            model=active_configuration.model,
            dimensions=(
                active_configuration.dimensions
            ),
            texts=[
                prepared_question,
            ],
            usage_feature="document_query_embedding",
        )

    except DocumentEmbeddingError:
        raise

    except Exception as error:
        raise DocumentEmbeddingError(
            "The embedding provider could not process "
            "the document question."
        ) from error

    if len(vectors) != 1:
        raise DocumentEmbeddingError(
            "The embedding provider returned an unexpected "
            "number of question vectors."
        )

    question_vector = normalize_vector(
        vectors[0]
    )

    if (
        len(question_vector)
        != active_configuration.dimensions
    ):
        raise DocumentEmbeddingError(
            "The question embedding has unexpected dimensions."
        )

    return (
        question_vector,
        active_configuration,
    )