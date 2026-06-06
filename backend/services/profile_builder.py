from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import GithubCache, Profile
from backend.services.cv_parser import extract_text_from_file
from backend.services.github_client import fetch_readme_with_meta

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


def _assemble_merged(yaml_data: str, cv_text: str, github_data: dict[str, str]) -> str:
    parts = ["## Candidate Profile (YAML)\n" + yaml_data]
    if cv_text.strip():
        parts.append("## CV Text\n" + cv_text[:8000])
    for repo, readme in github_data.items():
        if readme.strip():
            parts.append(f"## GitHub: {repo}\n" + readme[:3000])
    return "\n\n---\n\n".join(parts)


def build_compact_profile(yaml_text: str, cv_text: str) -> str:
    """Compact profile for early-stage agents (job_parser, match_scorer).

    Contains only YAML + first 500 chars of CV. Omits GitHub READMEs,
    which are large and not needed for parsing/scoring.
    """
    parts = ["## Candidate Profile (YAML)\n" + yaml_text]
    if cv_text.strip():
        parts.append("## CV Summary\n" + cv_text[:500])
    return "\n\n---\n\n".join(parts)


def _read_repos(yaml_path: str) -> tuple[str, list[str]]:
    """Return (raw yaml text, list of 'owner/repo' strings from featured_projects)."""
    path = Path(yaml_path)
    if not path.exists():
        logger.warning("Profile YAML not found at %s; using starter profile", yaml_path)
        yaml_text = _DEFAULT_PROFILE_YAML
    else:
        yaml_text = path.read_text()
    profile_data = yaml.safe_load(yaml_text) or {}
    repos = [
        p["repo"]
        for p in profile_data.get("featured_projects", [])
        if isinstance(p, dict) and "repo" in p
    ]
    return yaml_text, repos


async def build_profile(
    db: AsyncSession,
    yaml_path: str | None = None,
    cv_path: str | None = None,
    user_id: str | None = None,
) -> Profile:
    """Build a Profile row from YAML + CV + whatever is in github_cache.

    Does NOT fetch from GitHub. Call refresh_github_cache() first to populate the cache.
    Logs a warning and surfaces it if the cache is empty.
    """
    yaml_path = yaml_path or settings.profile_yaml_path
    cv_path = cv_path or settings.cv_path

    yaml_text, _ = _read_repos(yaml_path)
    cv_text = await extract_text_from_file(cv_path)

    # Read github_cache. Only rows with real README content count as GitHub data —
    # empty-content rows (fetched but blank) are filtered out so "has GitHub content"
    # is a single, honest signal used both here and in _profile_response.
    cache_rows = (await db.execute(select(GithubCache))).scalars().all()
    github_readmes: dict[str, str] = {
        f"{r.owner}/{r.repo_name}": r.readme_content
        for r in cache_rows
        if r.readme_content and r.readme_content.strip()
    }

    if not github_readmes:
        logger.warning(
            "GitHub cache is empty — merged_profile built without GitHub data. "
            "Run POST /api/profile/refresh/github to populate it."
        )

    # Derive github_last_fetched_at from the most recent cache row
    max_fetched: datetime | None = (
        await db.execute(select(func.max(GithubCache.fetched_at)))
    ).scalar_one_or_none()

    merged = _assemble_merged(yaml_text, cv_text, github_readmes)

    profile = Profile(
        yaml_data=yaml_text,
        cv_text=cv_text,
        github_data=json.dumps(github_readmes),
        merged_profile=merged,
        last_refreshed_at=datetime.now(timezone.utc),
        github_last_fetched_at=max_fetched,
        user_id=user_id,
    )
    db.add(profile)
    await db.flush()
    return profile


async def refresh_github_cache(db: AsyncSession, user_id: str | None = None) -> tuple[Profile, int]:
    """Fetch all repos from GitHub, update github_cache, rebuild merged_profile.

    Returns (new Profile row, number of repos updated).
    Hard-deletes cache rows for repos no longer in featured_projects.
    """
    yaml_path = settings.profile_yaml_path
    _, repos = _read_repos(yaml_path)

    # Fetch all repos concurrently
    fetch_results: list[tuple[str, str | None]] = list(
        await asyncio.gather(*[fetch_readme_with_meta(r) for r in repos])
    )

    now = datetime.now(timezone.utc)
    repo_set = set(repos)

    # Hard-delete cache rows for repos no longer in YAML
    existing_rows = (await db.execute(select(GithubCache))).scalars().all()
    for row in existing_rows:
        if f"{row.owner}/{row.repo_name}" not in repo_set:
            await db.delete(row)

    # Upsert cache rows for current repos
    repos_updated = 0
    for repo, (content, last_modified) in zip(repos, fetch_results):
        try:
            owner, repo_name = repo.split("/", 1)
        except ValueError:
            logger.warning("Skipping malformed repo string: %r", repo)
            continue

        existing = (
            await db.execute(
                select(GithubCache).where(
                    GithubCache.owner == owner,
                    GithubCache.repo_name == repo_name,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            db.add(
                GithubCache(
                    owner=owner,
                    repo_name=repo_name,
                    readme_content=content,
                    fetched_at=now,
                    last_modified=last_modified,
                )
            )
        else:
            existing.readme_content = content
            existing.fetched_at = now
            existing.last_modified = last_modified

        repos_updated += 1

    await db.flush()

    profile = await build_profile(db, user_id=user_id)
    return profile, repos_updated


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
