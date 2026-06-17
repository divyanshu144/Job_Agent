from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import MemoryChunk, Profile
from backend.config import settings
from backend.services.profile_builder import (
    build_compact_profile,
    build_profile_review_text,
    parse_profile_review_data,
)

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}")
_VECTOR_DIMS = 512
_STOPWORDS = {
    "and",
    "are",
    "for",
    "from",
    "have",
    "into",
    "that",
    "the",
    "this",
    "with",
    "you",
    "your",
    "will",
    "role",
    "job",
    "candidate",
    "experience",
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source: str
    source_ref: str | None
    score: float
    metadata: dict[str, Any]


def tokenize(text: str) -> list[str]:
    return [
        token.lower().strip(".-")
        for token in _TOKEN_RE.findall(text)
        if token.lower() not in _STOPWORDS and len(token) > 1
    ]


def sparse_vector(text: str) -> dict[str, float]:
    counts: dict[str, float] = {}
    for token in tokenize(text):
        bucket = str(int(hashlib.sha256(token.encode()).hexdigest(), 16) % _VECTOR_DIMS)
        counts[bucket] = counts.get(bucket, 0.0) + 1.0
    norm = math.sqrt(sum(value * value for value in counts.values()))
    if norm == 0:
        return {}
    return {key: round(value / norm, 6) for key, value in counts.items()}


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(key, 0.0) for key, value in a.items())


def dense_cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    a_norm = math.sqrt(sum(x * x for x in a))
    b_norm = math.sqrt(sum(y * y for y in b))
    if a_norm == 0 or b_norm == 0:
        return 0.0
    return dot / (a_norm * b_norm)


async def embed_texts(texts: list[str]) -> list[list[float]] | None:
    if settings.embedding_provider.lower() != "openai" or not settings.openai_api_key:
        return None
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("OpenAI package is not installed; semantic embeddings disabled")
        return None
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=settings.embedding_dimensions,
    )
    ordered = sorted(response.data, key=lambda item: item.index)
    return [list(item.embedding) for item in ordered]


async def _pgvector_available(db: AsyncSession) -> bool:
    if not settings.pgvector_enabled:
        return False
    try:
        return bool(
            (
                await db.execute(
                    text("select exists(select 1 from pg_extension where extname = 'vector')")
                )
            ).scalar_one()
        )
    except Exception:
        return False


def _split_text(text: str, *, max_chars: int = 900) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
            continue
        for start in range(0, len(paragraph), max_chars):
            chunk = paragraph[start : start + max_chars].strip()
            if chunk:
                chunks.append(chunk)
    return chunks


def profile_memory_chunks(profile: Profile) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    review = parse_profile_review_data(profile.profile_review_data)
    review_text = build_profile_review_text(review)
    if review_text.strip():
        for idx, text in enumerate(_split_text(review_text)):
            chunks.append(
                {
                    "namespace": "/candidate/profile_review",
                    "source": "profile_review",
                    "source_ref": f"profile_review:{idx}",
                    "text": text,
                    "metadata": {"profile_id": profile.id, "kind": "profile_review"},
                }
            )
    if profile.yaml_data.strip():
        chunks.append(
            {
                "namespace": "/candidate/profile",
                "source": "profile_yaml",
                "source_ref": "profile_yaml",
                "text": profile.yaml_data,
                "metadata": {"profile_id": profile.id, "kind": "profile_yaml"},
            }
        )
    for idx, text in enumerate(_split_text(profile.cv_text)):
        chunks.append(
            {
                "namespace": "/raw/resume",
                "source": "cv_text",
                "source_ref": f"cv_text:{idx}",
                "text": text,
                "metadata": {"profile_id": profile.id, "kind": "resume"},
            }
        )
    return chunks


async def write_profile_memory(db: AsyncSession, profile: Profile) -> None:
    await db.execute(delete(MemoryChunk).where(MemoryChunk.profile_id == profile.id))
    items = profile_memory_chunks(profile)
    embeddings = await embed_texts([item["text"] for item in items])
    rows: list[MemoryChunk] = []
    for idx, item in enumerate(items):
        embedding = embeddings[idx] if embeddings else None
        row = MemoryChunk(
            user_id=profile.user_id,
            profile_id=profile.id,
            namespace=item["namespace"],
            source=item["source"],
            source_ref=item["source_ref"],
            text=item["text"],
            metadata_json=json.dumps(item["metadata"]),
            sparse_vector_json=json.dumps(sparse_vector(item["text"])),
            embedding_model=settings.embedding_model if embedding else None,
            embedding_json=json.dumps(embedding) if embedding else None,
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    if embeddings and await _pgvector_available(db):
        for row, embedding in zip(rows, embeddings):
            await db.execute(
                text(
                    """
                    UPDATE memory_chunks
                    SET embedding_vector = CAST(:embedding AS vector)
                    WHERE id = :id
                    """
                ),
                {"id": row.id, "embedding": _vector_literal(embedding)},
            )
    await db.flush()


async def ensure_profile_memory(db: AsyncSession, profile: Profile) -> None:
    count = (
        await db.execute(
            select(func.count())
            .select_from(MemoryChunk)
            .where(MemoryChunk.profile_id == profile.id)
        )
    ).scalar_one()
    if count == 0:
        await write_profile_memory(db, profile)


async def retrieve_profile_memory(
    db: AsyncSession,
    profile: Profile,
    query: str,
    *,
    limit: int = 6,
) -> list[RetrievedChunk]:
    await ensure_profile_memory(db, profile)
    semantic = await _retrieve_semantic(db, profile, query, limit=limit)
    if semantic:
        return semantic
    query_vector = sparse_vector(query)
    rows = (
        (await db.execute(select(MemoryChunk).where(MemoryChunk.profile_id == profile.id)))
        .scalars()
        .all()
    )
    scored: list[RetrievedChunk] = []
    for row in rows:
        vector = json.loads(row.sparse_vector_json or "{}")
        score = cosine_similarity(query_vector, vector)
        if score <= 0:
            continue
        scored.append(
            RetrievedChunk(
                text=row.text,
                source=row.source,
                source_ref=row.source_ref,
                score=score,
                metadata=json.loads(row.metadata_json or "{}"),
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:limit]


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


async def _retrieve_semantic(
    db: AsyncSession,
    profile: Profile,
    query: str,
    *,
    limit: int,
) -> list[RetrievedChunk]:
    query_embeddings = await embed_texts([query])
    if not query_embeddings:
        return []
    query_embedding = query_embeddings[0]
    if await _pgvector_available(db):
        try:
            async with db.begin_nested():
                result = await db.execute(
                    text(
                        """
                        SELECT id, source, source_ref, text, metadata_json,
                               1 - (embedding_vector <=> CAST(:query AS vector)) AS score
                        FROM memory_chunks
                        WHERE profile_id = :profile_id
                          AND embedding_vector IS NOT NULL
                        ORDER BY embedding_vector <=> CAST(:query AS vector)
                        LIMIT :limit
                        """
                    ),
                    {
                        "profile_id": profile.id,
                        "query": _vector_literal(query_embedding),
                        "limit": limit,
                    },
                )
                rows = list(result)
            return [
                RetrievedChunk(
                    text=row.text,
                    source=row.source,
                    source_ref=row.source_ref,
                    score=float(row.score or 0.0),
                    metadata=json.loads(row.metadata_json or "{}"),
                )
                for row in rows
            ]
        except Exception as e:
            logger.warning("pgvector retrieval failed; falling back to JSON embeddings: %s", e)

    rows = (
        (
            await db.execute(
                select(MemoryChunk).where(
                    MemoryChunk.profile_id == profile.id,
                    MemoryChunk.embedding_json.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    scored: list[RetrievedChunk] = []
    for row in rows:
        embedding = json.loads(row.embedding_json or "[]")
        score = dense_cosine_similarity(query_embedding, embedding)
        if score <= 0:
            continue
        scored.append(
            RetrievedChunk(
                text=row.text,
                source=row.source,
                source_ref=row.source_ref,
                score=score,
                metadata=json.loads(row.metadata_json or "{}"),
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:limit]


async def build_retrieved_profile_context(
    db: AsyncSession,
    profile: Profile,
    query: str,
    *,
    limit: int = 6,
) -> str:
    chunks = await retrieve_profile_memory(db, profile, query, limit=limit)
    return format_retrieved_profile_context(profile, chunks)


def format_retrieved_profile_context(profile: Profile, chunks: list[RetrievedChunk]) -> str:
    compact = build_compact_profile(profile.yaml_data, profile.cv_text)
    if not chunks:
        return compact
    lines = ["## Retrieved Candidate Evidence"]
    for idx, chunk in enumerate(chunks, start=1):
        lines.append(
            f"[{idx}] source={chunk.source}"
            f" ref={chunk.source_ref or 'unknown'}"
            f" score={chunk.score:.3f}\n{chunk.text}"
        )
    lines.append("## Compact Candidate Profile")
    lines.append(compact)
    return "\n\n".join(lines)
