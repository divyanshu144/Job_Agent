from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.services.ats_client import fetch_ats_jobs
from backend.services.hn_client import RawJob

logger = logging.getLogger(__name__)

# Manual target list: [{"name", "ats": greenhouse|lever|ashby, "slug"}]
_TARGET_FILE = Path("assets/target_companies.json")


def _load_targets() -> list[dict[str, Any]]:
    """Read the target-company list. Returns [] if the file is missing or invalid."""
    try:
        data = json.loads(_TARGET_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        logger.warning("Target company list unavailable (%s): %s", _TARGET_FILE, exc)
        return []
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


async def fetch_target_jobs() -> list[RawJob]:
    """Query the ATS board for each manually-listed target company. Malformed
    entries and per-company fetch errors are skipped, not fatal."""
    jobs: list[RawJob] = []
    for entry in _load_targets():
        ats = entry.get("ats")
        slug = entry.get("slug")
        if not ats or not slug:
            logger.warning("Skipping malformed target entry: %r", entry)
            continue
        try:
            jobs.extend(await fetch_ats_jobs(ats, slug))
        except Exception as exc:  # one target must never abort the rest
            logger.warning("Target %s (%s/%s) failed: %s", entry.get("name"), ats, slug, exc)
            continue
    return jobs
