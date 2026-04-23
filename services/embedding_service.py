"""
Embedding Service

Single responsibility: convert text strings into 1536-dim vectors
using OpenAI's text-embedding-3-small model.

All other services go through here — never call the OpenAI client directly.
This makes it trivial to swap the embedding model in the future.
"""

from __future__ import annotations
from openai import AsyncOpenAI

from core.config import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536


async def get_embedding(text: str) -> list[float]:
    """
    Return the embedding vector for a single text string.
    Text is truncated to 8191 tokens by the API automatically.
    """
    text = text.replace("\n", " ").strip()
    if not text:
        raise ValueError("Cannot embed empty text")

    client = _get_client()
    response = await client.embeddings.create(
        input=text,
        model=EMBEDDING_MODEL,
    )
    return response.data[0].embedding


MAX_CHUNKS_PER_BATCH = 300  # ~800 tokens/chunk × 300 = 240k, safely under OpenAI's 300k limit


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed multiple texts, automatically splitting into sub-batches to stay
    under OpenAI's 300k tokens-per-request limit.
    """
    texts = [t.replace("\n", " ").strip() for t in texts]
    texts = [t for t in texts if t]  # drop empty strings

    if not texts:
        return []

    client = _get_client()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), MAX_CHUNKS_PER_BATCH):
        batch = texts[i : i + MAX_CHUNKS_PER_BATCH]
        response = await client.embeddings.create(
            input=batch,
            model=EMBEDDING_MODEL,
        )
        batch_embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings