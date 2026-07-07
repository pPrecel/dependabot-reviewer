import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.update_branch = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_update_branch_done(mock_client):
    """Branch updated successfully → status done, branch_updated True."""
    mock_client.update_branch.return_value = {"message": "Updating pull request branch."}

    with patch("dependabot_mcp.server.get_client", return_value=mock_client):
        from dependabot_mcp.server import update_branch
        result = await update_branch(
            host="github.com",
            token="tok",
            repo="org/repo",
            pr_number=42,
        )

    assert result["status"] == "done"
    assert result["branch_updated"] is True
    assert result["message"] == ""
    mock_client.update_branch.assert_awaited_once_with("org/repo", 42)


@pytest.mark.asyncio
async def test_update_branch_needs_manual_rebase(mock_client):
    """422 from GitHub → status needs_manual_rebase, branch_updated False."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = 422
    response.text = "Merge conflict"
    mock_client.update_branch.side_effect = httpx.HTTPStatusError(
        "422", request=MagicMock(), response=response
    )

    with patch("dependabot_mcp.server.get_client", return_value=mock_client):
        from dependabot_mcp.server import update_branch
        result = await update_branch(
            host="github.com",
            token="tok",
            repo="org/repo",
            pr_number=42,
        )

    assert result["status"] == "needs_manual_rebase"
    assert result["branch_updated"] is False
    assert "conflict" in result["message"].lower() or "manual" in result["message"].lower()


@pytest.mark.asyncio
async def test_update_branch_already_up_to_date(mock_client):
    """GitHub 422 with 'already up-to-date' body → still done (no conflict)."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = 422
    response.text = "already up-to-date"
    mock_client.update_branch.side_effect = httpx.HTTPStatusError(
        "422", request=MagicMock(), response=response
    )

    with patch("dependabot_mcp.server.get_client", return_value=mock_client):
        from dependabot_mcp.server import update_branch
        result = await update_branch(
            host="github.com",
            token="tok",
            repo="org/repo",
            pr_number=42,
        )

    assert result["status"] == "done"
    assert result["branch_updated"] is False
    assert result["message"] != ""  # should explain it was already up to date
