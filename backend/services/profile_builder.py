from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import Profile, User
from backend.schemas import ExtractedProfile, ProfileReviewData, ProfileReviewEducation
from backend.services.cv_parser import extract_text_from_file

logger = logging.getLogger(__name__)


class ProfileNotConfiguredError(Exception):
    """A non-admin user has no owned Profile row. Regular users must NEVER fall
    back to the shared profile_yaml_path/cv_path files (hard tenant boundary —
    those serve the admin's single-candidate flow only)."""


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


def default_profile_yaml() -> str:
    return _DEFAULT_PROFILE_YAML


def parse_profile_review_data(raw_text: str) -> ProfileReviewData:
    if not raw_text.strip():
        return ProfileReviewData()
    try:
        return ProfileReviewData.model_validate(json.loads(raw_text))
    except (json.JSONDecodeError, TypeError, ValueError):
        return ProfileReviewData()


def serialize_profile_review_data(review_data: ProfileReviewData) -> str:
    return review_data.model_dump_json()


def _clean_list(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]


def build_profile_review_text(review_data: ProfileReviewData) -> str:
    sections: list[str] = []

    if review_data.target_role.strip():
        sections.append("Target Role\n" + review_data.target_role.strip())

    skills = _clean_list(review_data.key_skills)
    if skills:
        sections.append("Key Skills\n" + "\n".join(f"- {skill}" for skill in skills))

    projects: list[str] = []
    for project in review_data.projects:
        name = project.name.strip()
        description = project.description.strip()
        highlights = _clean_list(project.highlights)
        if not (name or description or highlights):
            continue
        lines = [name or "Project"]
        if description:
            lines.append(description)
        lines.extend(f"- {highlight}" for highlight in highlights)
        projects.append("\n".join(lines))
    if projects:
        sections.append("Projects\n" + "\n\n".join(projects))

    experience_items: list[str] = []
    for item in review_data.experience:
        heading = " - ".join(part for part in [item.role.strip(), item.company.strip()] if part)
        dates = item.dates.strip()
        highlights = _clean_list(item.highlights)
        if not (heading or dates or highlights):
            continue
        lines = [heading or "Experience"]
        if dates:
            lines.append(dates)
        lines.extend(f"- {highlight}" for highlight in highlights)
        experience_items.append("\n".join(lines))
    if experience_items:
        sections.append("Experience\n" + "\n\n".join(experience_items))

    education_items: list[str] = []
    for edu in review_data.education:
        degree_line = " - ".join(
            part for part in [edu.degree.strip(), edu.field_of_study.strip()] if part
        )
        lines = [edu.institution.strip()] if edu.institution.strip() else []
        if degree_line:
            lines.append(degree_line)
        if edu.dates.strip():
            lines.append(edu.dates.strip())
        if lines:
            education_items.append("\n".join(lines))
    if education_items:
        sections.append("Education\n" + "\n\n".join(education_items))

    links: list[str] = []
    for link in review_data.links:
        label = link.label.strip()
        url = link.url.strip()
        if label and url:
            links.append(f"- {label}: {url}")
        elif url:
            links.append(f"- {url}")
    if links:
        sections.append("Links\n" + "\n".join(links))

    preferences = review_data.work_preferences
    pref_lines: list[str] = []
    locations = _clean_list(preferences.locations)
    role_types = _clean_list(preferences.role_types)
    industries = _clean_list(preferences.industries)
    if locations:
        pref_lines.append("Locations: " + ", ".join(locations))
    if preferences.remote and preferences.remote.strip():
        pref_lines.append("Remote: " + preferences.remote.strip())
    if role_types:
        pref_lines.append("Role types: " + ", ".join(role_types))
    if industries:
        pref_lines.append("Industries: " + ", ".join(industries))
    if pref_lines:
        sections.append("Work Preferences\n" + "\n".join(pref_lines))

    return "\n\n".join(sections)


def _assemble_merged(
    yaml_data: str, cv_text: str, profile_review_data: str | ProfileReviewData | None = None
) -> str:
    parts = ["## Candidate Profile (YAML)\n" + yaml_data]
    if profile_review_data is not None:
        review_data = (
            profile_review_data
            if isinstance(profile_review_data, ProfileReviewData)
            else parse_profile_review_data(profile_review_data)
        )
        review_text = build_profile_review_text(review_data)
        if review_text.strip():
            parts.append("## Profile Review\n" + review_text)
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


def extracted_profile_to_yaml(profile: ExtractedProfile) -> str:
    """Render an ExtractedProfile as YAML matching the candidate_profile schema.
    Does NOT emit search_profiles — that is left to the user/discovery."""
    data = {
        "identity": {
            "name": profile.identity.name,
            "headline": profile.identity.headline,
            "location": profile.identity.location,
        },
        "core_skills": {
            "languages": list(profile.core_skills.languages),
            "frameworks": list(profile.core_skills.frameworks),
            "tools": list(profile.core_skills.tools),
        },
        "experience": [
            {
                "company": e.company,
                "role": e.role,
                "dates": e.dates,
                "highlights": list(e.highlights),
            }
            for e in profile.experience
        ],
        "featured_projects": [
            {"name": p.name, "themes": list(p.themes)} for p in profile.featured_projects
        ],
        "education": [
            {
                "institution": e.institution,
                "degree": e.degree,
                "field_of_study": e.field_of_study,
                "dates": e.dates,
            }
            for e in profile.education
        ],
    }
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def review_seed_from_extracted(
    extracted: ExtractedProfile, existing: ProfileReviewData
) -> ProfileReviewData:
    """Seed the user-editable review form from a freshly extracted CV, without
    clobbering data the user has already entered.

    Only fills `key_skills` / `education` when the user's current review has none,
    so re-uploading a CV never overwrites confirmed edits. Skills are flattened from
    the extractor's buckets (languages + frameworks + tools), de-duplicated in order.
    """
    seed = existing.model_copy(deep=True)

    if not seed.key_skills:
        skills = (
            list(extracted.core_skills.languages)
            + list(extracted.core_skills.frameworks)
            + list(extracted.core_skills.tools)
        )
        seen: set[str] = set()
        deduped: list[str] = []
        for skill in skills:
            cleaned = skill.strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                deduped.append(cleaned)
        seed.key_skills = deduped

    if not seed.education:
        seed.education = [
            ProfileReviewEducation(
                institution=e.institution,
                degree=e.degree,
                field_of_study=e.field_of_study,
                dates=e.dates,
            )
            for e in extracted.education
        ]

    return seed


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
    profile_review_data: str | ProfileReviewData | None = None,
    review_status: str = "draft",
    reviewed_at: datetime | None = None,
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

    review_text = (
        serialize_profile_review_data(profile_review_data)
        if isinstance(profile_review_data, ProfileReviewData)
        else (profile_review_data or "{}")
    )
    merged = _assemble_merged(yaml_text, cv_text, review_text if user_id else None)

    profile = Profile(
        yaml_data=yaml_text,
        cv_text=cv_text,
        profile_review_data=review_text,
        review_status=review_status,
        reviewed_at=reviewed_at,
        merged_profile=merged,
        last_refreshed_at=datetime.now(timezone.utc),
        user_id=user_id,
    )
    db.add(profile)
    await db.flush()
    from backend.services.memory import write_profile_memory

    await write_profile_memory(db, profile)
    return profile


async def build_profile_from_text(
    db: AsyncSession,
    *,
    yaml_text: str,
    cv_text: str,
    user_id: str,
    profile_review_data: str | ProfileReviewData | None = None,
    review_status: str = "draft",
    reviewed_at: datetime | None = None,
) -> Profile:
    """Create a user-owned Profile row from already-parsed content.

    Used for authenticated uploads so user CV bytes never write through the
    legacy shared settings.cv_path file.
    """
    review_text = (
        serialize_profile_review_data(profile_review_data)
        if isinstance(profile_review_data, ProfileReviewData)
        else (profile_review_data or "{}")
    )
    merged = _assemble_merged(yaml_text, cv_text, review_text)
    profile = Profile(
        yaml_data=yaml_text,
        cv_text=cv_text,
        profile_review_data=review_text,
        review_status=review_status,
        reviewed_at=reviewed_at,
        merged_profile=merged,
        last_refreshed_at=datetime.now(timezone.utc),
        user_id=user_id,
    )
    db.add(profile)
    await db.flush()
    from backend.services.memory import write_profile_memory

    await write_profile_memory(db, profile)
    return profile


async def get_owned_profile(db: AsyncSession, user_id: str) -> Profile | None:
    """The user's own newest Profile row, or None. Never reads shared files."""
    return (
        await db.execute(
            select(Profile)
            .where(Profile.user_id == user_id)
            .order_by(Profile.last_refreshed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_or_build_profile(db: AsyncSession, user_id: str | None = None) -> Profile:
    """Resolve the profile for a pipeline run.

    user_id set: the user's OWN row, or — for the admin only — a fallback build
    from the shared yaml/cv files. A regular user with no row raises
    ProfileNotConfiguredError instead (zero LLM work happens downstream).
    user_id None: legacy/discovery scope, newest row with shared-file fallback.
    """
    if user_id:
        owned = await get_owned_profile(db, user_id)
        if owned is not None:
            return owned
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None or not user.is_admin:
            raise ProfileNotConfiguredError(
                "Complete your profile first — upload your CV before running analyses."
            )
        return await build_profile(db, user_id=user_id)  # admin-only shared fallback

    profile = (
        await db.execute(select(Profile).order_by(Profile.last_refreshed_at.desc()).limit(1))
    ).scalar_one_or_none()
    if profile is None:
        profile = await build_profile(db)
    return profile
