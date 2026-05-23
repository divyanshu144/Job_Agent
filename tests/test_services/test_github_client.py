import base64
from unittest.mock import AsyncMock, MagicMock, patch


async def test_fetch_readme_success():
    encoded = base64.b64encode(b"# DocChat\nA RAG project").decode()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"content": encoded, "encoding": "base64"}

    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_resp)
        from backend.services.github_client import fetch_readme

        result = await fetch_readme("divyanshu144/docchat")

    assert "DocChat" in result


async def test_fetch_readme_404_returns_empty():
    from httpx import HTTPStatusError

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock(status_code=404)
    )

    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_resp)
        from backend.services.github_client import fetch_readme

        result = await fetch_readme("divyanshu144/nonexistent")

    assert result == ""


async def test_fetch_all_readmes_returns_dict():
    with patch("backend.services.github_client.fetch_readme", new_callable=AsyncMock) as mock_fr:
        mock_fr.return_value = "# README"
        from backend.services.github_client import fetch_all_readmes

        result = await fetch_all_readmes(["a/b", "c/d"])

    assert result == {"a/b": "# README", "c/d": "# README"}
