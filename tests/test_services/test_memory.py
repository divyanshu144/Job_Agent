from __future__ import annotations

from backend.models import MemoryChunk, Profile
from backend.schemas import ProfileReviewData
from backend.services.memory import (
    build_retrieved_profile_context,
    dense_cosine_similarity,
    retrieve_profile_memory,
    sparse_vector,
    write_profile_memory,
)


def test_sparse_vector_is_normalized_and_deterministic():
    first = sparse_vector("Python FastAPI Python")
    second = sparse_vector("Python FastAPI Python")

    assert first == second
    assert first


def test_dense_cosine_similarity():
    assert dense_cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert dense_cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


async def test_write_profile_memory_persists_chunks(session):
    profile = Profile(
        yaml_data="core_skills:\n  languages: [Python]",
        cv_text="Built FastAPI services for data processing.",
        merged_profile="merged",
        profile_review_data=ProfileReviewData(
            target_role="Backend Engineer",
            key_skills=["Python", "FastAPI"],
        ).model_dump_json(),
    )
    session.add(profile)
    await session.flush()

    await write_profile_memory(session, profile)
    await session.commit()

    rows = (await session.execute(MemoryChunk.__table__.select())).all()
    assert rows


async def test_retrieve_profile_memory_returns_relevant_chunks(session):
    profile = Profile(
        yaml_data="core_skills:\n  languages: [Python]",
        cv_text="Built FastAPI APIs and PostgreSQL services.\n\nDesigned React dashboards.",
        merged_profile="merged",
    )
    session.add(profile)
    await session.flush()
    await write_profile_memory(session, profile)

    chunks = await retrieve_profile_memory(session, profile, "FastAPI backend API", limit=2)

    assert chunks
    assert "FastAPI" in chunks[0].text


async def test_build_retrieved_profile_context_includes_provenance(session):
    profile = Profile(
        yaml_data="core_skills:\n  languages: [Python]",
        cv_text="Built FastAPI APIs and PostgreSQL services.",
        merged_profile="merged",
    )
    session.add(profile)
    await session.flush()
    await write_profile_memory(session, profile)

    context = await build_retrieved_profile_context(session, profile, "FastAPI", limit=1)

    assert "## Retrieved Candidate Evidence" in context
    assert "source=" in context


async def test_semantic_retrieval_uses_embedding_json_fallback(session, monkeypatch):
    import backend.services.memory as memory

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vectors.append([1.0, 0.0] if "FastAPI" in text else [0.0, 1.0])
        return vectors

    async def no_pgvector(_db) -> bool:
        return False

    monkeypatch.setattr(memory, "embed_texts", fake_embed)
    monkeypatch.setattr(memory, "_pgvector_available", no_pgvector)

    profile = Profile(
        yaml_data="core_skills:\n  languages: [Python]",
        cv_text="Built FastAPI APIs.\n\nDesigned React dashboards.",
        merged_profile="merged",
    )
    session.add(profile)
    await session.flush()
    await write_profile_memory(session, profile)

    chunks = await retrieve_profile_memory(session, profile, "FastAPI", limit=1)

    assert len(chunks) == 1
    assert "FastAPI" in chunks[0].text


async def test_pgvector_failure_falls_back_to_embedding_json(session, monkeypatch):
    import backend.services.memory as memory

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vectors.append([1.0, 0.0] if "FastAPI" in text else [0.0, 1.0])
        return vectors

    async def no_pgvector(_db) -> bool:
        return False

    async def yes_pgvector(_db) -> bool:
        return True

    monkeypatch.setattr(memory, "embed_texts", fake_embed)
    monkeypatch.setattr(memory, "_pgvector_available", no_pgvector)

    profile = Profile(
        yaml_data="core_skills:\n  languages: [Python]",
        cv_text="Built FastAPI APIs.\n\nDesigned React dashboards.",
        merged_profile="merged",
    )
    session.add(profile)
    await session.flush()
    await write_profile_memory(session, profile)

    monkeypatch.setattr(memory, "_pgvector_available", yes_pgvector)
    chunks = await retrieve_profile_memory(session, profile, "FastAPI", limit=1)

    assert len(chunks) == 1
    assert "FastAPI" in chunks[0].text
