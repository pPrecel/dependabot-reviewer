import pytest
import respx
import httpx
from dependabot_mcp.server import get_branch_ci_status


@respx.mock
async def test_get_branch_ci_status_passing():
    respx.get("https://api.github.com/repos/owner/repo/git/ref/heads/main").mock(
        return_value=httpx.Response(200, json={
            "object": {"sha": "abc123", "type": "commit"}
        })
    )
    respx.get("https://api.github.com/repos/owner/repo/commits/abc123/check-runs").mock(
        return_value=httpx.Response(200, json={
            "check_runs": [
                {"name": "build", "status": "completed", "conclusion": "success"},
                {"name": "test-unit", "status": "completed", "conclusion": "success"},
            ]
        })
    )
    result = await get_branch_ci_status(host="github.com", token="tok", repo="owner/repo", branch="main")
    assert result["sha"] == "abc123"
    assert result["branch"] == "main"
    assert result["ci_status"] == "passing"
    assert result["failing_checks"] == []
    assert result["total_checks"] == 2
    assert result["passing_checks"] == 2


@respx.mock
async def test_get_branch_ci_status_failing():
    respx.get("https://api.github.com/repos/owner/repo/git/ref/heads/main").mock(
        return_value=httpx.Response(200, json={
            "object": {"sha": "def456", "type": "commit"}
        })
    )
    respx.get("https://api.github.com/repos/owner/repo/commits/def456/check-runs").mock(
        return_value=httpx.Response(200, json={
            "check_runs": [
                {"name": "build", "status": "completed", "conclusion": "failure"},
                {"name": "test-unit", "status": "completed", "conclusion": "success"},
                {"name": "lint", "status": "completed", "conclusion": "timed_out"},
            ]
        })
    )
    result = await get_branch_ci_status(host="github.com", token="tok", repo="owner/repo", branch="main")
    assert result["ci_status"] == "failing"
    assert len(result["failing_checks"]) == 2
    assert result["failing_checks"][0]["name"] == "build"
    assert result["failing_checks"][1]["name"] == "lint"
    assert result["total_checks"] == 3
    assert result["passing_checks"] == 1


@respx.mock
async def test_get_branch_ci_status_pending():
    respx.get("https://api.github.com/repos/owner/repo/git/ref/heads/main").mock(
        return_value=httpx.Response(200, json={
            "object": {"sha": "fff999", "type": "commit"}
        })
    )
    respx.get("https://api.github.com/repos/owner/repo/commits/fff999/check-runs").mock(
        return_value=httpx.Response(200, json={
            "check_runs": [
                {"name": "build", "status": "in_progress", "conclusion": None},
                {"name": "test-unit", "status": "completed", "conclusion": "success"},
            ]
        })
    )
    result = await get_branch_ci_status(host="github.com", token="tok", repo="owner/repo", branch="main")
    assert result["ci_status"] == "pending"
    assert result["failing_checks"] == []


@respx.mock
async def test_get_branch_ci_status_unknown_no_checks():
    respx.get("https://api.github.com/repos/owner/repo/git/ref/heads/main").mock(
        return_value=httpx.Response(200, json={
            "object": {"sha": "aaa000", "type": "commit"}
        })
    )
    respx.get("https://api.github.com/repos/owner/repo/commits/aaa000/check-runs").mock(
        return_value=httpx.Response(200, json={"check_runs": []})
    )
    result = await get_branch_ci_status(host="github.com", token="tok", repo="owner/repo", branch="main")
    assert result["ci_status"] == "unknown"
    assert result["total_checks"] == 0
