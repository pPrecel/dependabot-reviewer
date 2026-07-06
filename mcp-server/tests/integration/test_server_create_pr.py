import pytest
import respx
import httpx
from dependabot_mcp.server import get_branch_head_sha, create_pull_request


@respx.mock
async def test_get_branch_head_sha_returns_sha():
    respx.get("https://api.github.com/repos/owner/repo/git/ref/heads/main").mock(
        return_value=httpx.Response(200, json={
            "object": {"sha": "abc123def456"}
        })
    )
    result = await get_branch_head_sha(
        host="github.com",
        token="tok",
        repo="owner/repo",
        branch="main",
    )
    assert result == "abc123def456"


@respx.mock
async def test_get_branch_head_sha_404_raises():
    respx.get("https://api.github.com/repos/owner/repo/git/ref/heads/nonexistent").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        await get_branch_head_sha(
            host="github.com",
            token="tok",
            repo="owner/repo",
            branch="nonexistent",
        )


@respx.mock
async def test_create_pull_request_returns_pr():
    respx.post("https://api.github.com/repos/owner/repo/pulls").mock(
        return_value=httpx.Response(201, json={
            "number": 99,
            "html_url": "https://github.com/owner/repo/pull/99",
        })
    )
    result = await create_pull_request(
        host="github.com",
        token="tok",
        repo="owner/repo",
        title="fix: restore CI after dependency update",
        head="fix/dependabot-ci-short-desc",
        base="main",
        body="Automated fix.",
    )
    assert result["pr_number"] == 99
    assert result["pr_url"] == "https://github.com/owner/repo/pull/99"


@respx.mock
async def test_create_pull_request_on_ghes():
    respx.post("https://github.tools.sap/api/v3/repos/kyma/warden/pulls").mock(
        return_value=httpx.Response(201, json={
            "number": 42,
            "html_url": "https://github.tools.sap/kyma/warden/pull/42",
        })
    )
    result = await create_pull_request(
        host="github.tools.sap",
        token="tok",
        repo="kyma/warden",
        title="fix: restore CI",
        head="fix/ci-fix",
        base="main",
        body="Fix.",
    )
    assert result["pr_number"] == 42
