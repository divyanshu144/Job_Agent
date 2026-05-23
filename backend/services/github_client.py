from __future__ import annotations

import base64

import httpx

GITHUB_API = "https://api.github.com"


async def fetch_readme(repo: str) -> str:
    """Fetch decoded README text for a public repo. Returns '' on 404 or any error."""
    url = f"{GITHUB_API}/repos/{repo}/readme"
    headers = {"Accept": "application/vnd.github.v3+json"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return str(data.get("content", ""))
        except httpx.HTTPStatusError:
            return ""
        except Exception:
            return ""


async def fetch_readme_with_meta(repo: str) -> tuple[str, str | None]:
    """Fetch decoded README and Last-Modified header. Returns ('', None) on error."""
    url = f"{GITHUB_API}/repos/{repo}/readme"
    headers = {"Accept": "application/vnd.github.v3+json"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = (
                base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                if data.get("encoding") == "base64"
                else str(data.get("content", ""))
            )
            return content, resp.headers.get("Last-Modified")
        except httpx.HTTPStatusError:
            return "", None
        except Exception:
            return "", None


async def fetch_all_readmes(repos: list[str]) -> dict[str, str]:
    """Fetch READMEs for multiple repos concurrently."""
    import asyncio

    results = await asyncio.gather(*[fetch_readme(r) for r in repos])
    return dict(zip(repos, results))
