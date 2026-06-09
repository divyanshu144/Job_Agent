from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import Profile
from backend.services.cv_parser import extract_text_from_file

logger = logging.getLogger(__name__)


def profile_content_hash(merged_profile: str) -> str:
    """The single definition of 'profile identity' for caching — hashes the built
    profile *content*, not its rotating row id. Any content change yields a new hash;
    identical content (even across rebuilt rows) yields the same hash."""
    return hashlib.sha256(merged_profile.encode()).hexdigest()


_DEFAULT_PROFILE_YAML = """identity:
  name: Candidate
  headline: ""

core_skills:
  languages: []
  frameworks: []
  tools: []

featured_projects: []

search_profiles: []
"""


def _assemble_merged(yaml_data: str, cv_text: str) -> str:
    parts = ["## Candidate Profile (YAML)\n" + yaml_data]
    if cv_text.strip():
        parts.append("## CV Text\n" + cv_text[:8000])
    return "\n\n---\n\n".join(parts)


def build_compact_profile(yaml_text: str, cv_text: str) -> str:
    """Compact profile for early-stage agents (job_parser, match_scorer).

    Contains only YAML + first 500 chars of CV.
    """
    parts = ["## Candidate Profile (YAML)\n" + yaml_text]
    if cv_text.strip():
        parts.append("## CV Summary\n" + cv_text[:500])
    return "\n\n---\n\n".join(parts)


def _read_yaml(yaml_path: str) -> str:
    """Return the raw profile YAML text, falling back to the starter profile."""
    path = Path(yaml_path)
    if not path.exists():
        logger.warning("Profile YAML not found at %s; using starter profile", yaml_path)
        return _DEFAULT_PROFILE_YAML
    return path.read_text()


async def build_profile(
    db: AsyncSession,
    yaml_path: str | None = None,
    cv_path: str | None = None,
    user_id: str | None = None,
    cv_text: str | None = None,
) -> Profile:
    """Build a Profile row from YAML + CV.

    merged_profile is YAML + CV only — deterministic by construction, so its
    content hash (profile_content_hash) is a stable cache identity.
    """
    yaml_path = yaml_path or settings.profile_yaml_path
    cv_path = cv_path or settings.cv_path

    yaml_text = _read_yaml(yaml_path)
    if cv_text is None:
        cv_text = await extract_text_from_file(cv_path)

    merged = _assemble_merged(yaml_text, cv_text)

    profile = Profile(
        yaml_data=yaml_text,
        cv_text=cv_text,
        merged_profile=merged,
        last_refreshed_at=datetime.now(timezone.utc),
        user_id=user_id,
    )
    db.add(profile)
    await db.flush()
    return profile


async def build_profile_from_text(
    db: AsyncSession,
    *,
    yaml_text: str,
    cv_text: str,
    user_id: str,
) -> Profile:
    """Create a user-owned Profile row from already-parsed content.

    Used for authenticated uploads so user CV bytes never write through the
    legacy shared settings.cv_path file.
    """
    merged = _assemble_merged(yaml_text, cv_text)
    profile = Profile(
        yaml_data=yaml_text,
        cv_text=cv_text,
        merged_profile=merged,
        last_refreshed_at=datetime.now(timezone.utc),
        user_id=user_id,
    )
    db.add(profile)
    await db.flush()
    return profile


async def get_or_build_profile(db: AsyncSession, user_id: str | None = None) -> Profile:
    q = select(Profile).order_by(Profile.last_refreshed_at.desc()).limit(1)
    if user_id:
        q = (
            select(Profile)
            .where(Profile.user_id == user_id)
            .order_by(Profile.last_refreshed_at.desc())
            .limit(1)
        )
    result = await db.execute(q)
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = await build_profile(db, user_id=user_id)
    return profile
