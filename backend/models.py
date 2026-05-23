from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    yaml_data: Mapped[str] = mapped_column(Text)
    cv_text: Mapped[str] = mapped_column(Text, default="")
    github_data: Mapped[str] = mapped_column(Text, default="{}")
    merged_profile: Mapped[str] = mapped_column(Text, default="")
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    github_last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class GithubCache(Base):
    __tablename__ = "github_cache"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner: Mapped[str] = mapped_column(String, nullable=False)
    repo_name: Mapped[str] = mapped_column(String, nullable=False)
    readme_content: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_modified: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    __table_args__ = (UniqueConstraint("owner", "repo_name", name="uq_github_cache_repo"),)


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    jd_text: Mapped[str] = mapped_column(Text)
    profile_id: Mapped[str] = mapped_column(String, ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    partial: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluate_only: Mapped[bool] = mapped_column(Boolean, default=False)
    results: Mapped[list[JobResult]] = relationship("JobResult", back_populates="analysis")


class JobResult(Base):
    __tablename__ = "job_results"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(String, ForeignKey("analyses.id"))
    agent_name: Mapped[str] = mapped_column(String)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[Analysis] = relationship("Analysis", back_populates="results")
