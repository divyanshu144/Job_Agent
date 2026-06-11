from __future__ import annotations

from unittest.mock import AsyncMock, patch

from backend.services.targets_client import fetch_target_jobs


async def test_fetch_target_jobs_uses_passed_list():
    targets = [
        {"name": "Netlify", "ats": "lever", "slug": "netlify"},
        {"name": "Ramp", "ats": "ashby", "slug": "ramp"},
    ]
    with (
        patch(
            "backend.services.targets_client.fetch_ats_jobs",
            new_callable=AsyncMock,
            return_value=[],
        ) as fetch,
        patch("backend.services.targets_client._load_targets") as load_file,
    ):
        await fetch_target_jobs(targets)

    load_file.assert_not_called()  # explicit list bypasses the shared JSON file
    assert fetch.await_count == 2
    called = {(c.args[0], c.args[1]) for c in fetch.await_args_list}
    assert called == {("lever", "netlify"), ("ashby", "ramp")}


async def test_fetch_target_jobs_none_loads_file():
    with (
        patch(
            "backend.services.targets_client._load_targets",
            return_value=[{"name": "Stripe", "ats": "greenhouse", "slug": "stripe"}],
        ) as load_file,
        patch(
            "backend.services.targets_client.fetch_ats_jobs",
            new_callable=AsyncMock,
            return_value=[],
        ) as fetch,
    ):
        await fetch_target_jobs()  # no arg -> falls back to the file loader

    load_file.assert_called_once()
    fetch.assert_awaited_once_with("greenhouse", "stripe")
