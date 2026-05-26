from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

HN_ALGOLIA = "https://hn.algolia.com/api/v1"
_MIN_TEXT_LEN = 100


@dataclass
class RawJob:
    source_id: str
    source_url: str
    raw_text: str
    dedup_hash: str


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _month_start_ts() -> int:
    now = datetime.now(timezone.utc)
    return int(datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp())


async def _find_thread_id() -> str | None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{HN_ALGOLIA}/search",
                params={
                    "query": "Ask HN: Who is hiring?",
                    "tags": "story",
                    "numericFilters": f"created_at_i>{_month_start_ts()}",
                },
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            obj_id = hits[0].get("objectID") if hits else None
            return str(obj_id) if obj_id else None
    except httpx.HTTPError:
        return None


async def fetch_hn_jobs() -> list[RawJob]:
    """Fetch all top-level comments from the current month's HN hiring thread."""
    thread_id = await _find_thread_id()
    if thread_id is None:
        return []

    jobs: list[RawJob] = []
    page = 0
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                resp = await client.get(
                    f"{HN_ALGOLIA}/search",
                    params={
                        "tags": f"comment,story_{thread_id}",
                        "hitsPerPage": 200,
                        "page": page,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                hits = data.get("hits", [])
                if not hits:
                    break
                for hit in hits:
                    raw_html = hit.get("comment_text", "")
                    if not raw_html:
                        continue
                    text = _strip_html(raw_html)
                    if len(text) < _MIN_TEXT_LEN:
                        continue
                    obj_id = hit.get("objectID")
                    if not obj_id:
                        continue
                    obj_id = str(obj_id)
                    jobs.append(
                        RawJob(
                            source_id=obj_id,
                            source_url=f"https://news.ycombinator.com/item?id={obj_id}",
                            raw_text=text,
                            dedup_hash=hashlib.sha256(text.encode()).hexdigest(),
                        )
                    )
                # Use nbPages when present; fall back to empty-hits check for termination
                nb_pages = data.get("nbPages")
                if nb_pages is not None and page >= nb_pages - 1:
                    break
                page += 1
    except httpx.HTTPError:
        pass

    return jobs
