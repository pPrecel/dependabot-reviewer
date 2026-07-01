import base64

import pytest
import respx
import httpx
from dependabot_mcp.github_client import GithubClient


@pytest.fixture
def gh():
    return GithubClient(host="github.com", token="test-token")


@pytest.fixture
def ghes():
    return GithubClient(host="github.tools.sap", token="test-token")


def test_base_url_github_com(gh):
    assert str(gh._client.base_url) == "https://api.github.com/"


def test_base_url_ghes(ghes):
    assert str(ghes._client.base_url) == "https://github.tools.sap/api/v3/"


@respx.mock
async def test_search_prs(gh):
    respx.get("https://api.github.com/search/issues").mock(
        return_value=httpx.Response(200, json={
            "items": [
                {"number": 1, "repository_url": "https://api.github.com/repos/owner/repo",
                 "title": "bump foo", "html_url": "https://github.com/owner/repo/pull/1"}
            ]
        })
    )
    result = await gh.search_prs("is:open is:pr author:app/dependabot review-requested:@me")
    assert len(result) == 1
    assert result[0]["number"] == 1


@respx.mock
async def test_get_pr(gh):
    respx.get("https://api.github.com/repos/owner/repo/pulls/42").mock(
        return_value=httpx.Response(200, json={
            "number": 42, "mergeable_state": "clean",
            "auto_merge": {"merge_method": "squash"},
        })
    )
    result = await gh.get_pr("owner/repo", 42)
    assert result["number"] == 42


@respx.mock
async def test_get_pr_diff(gh):
    respx.get("https://api.github.com/repos/owner/repo/pulls/42").mock(
        return_value=httpx.Response(200, text="diff --git a/go.mod b/go.mod\n+foo")
    )
    result = await gh.get_pr_diff("owner/repo", 42)
    assert "go.mod" in result


@respx.mock
async def test_get_release(gh):
    respx.get("https://api.github.com/repos/owner/lib/releases/tags/v1.0.1").mock(
        return_value=httpx.Response(200, json={"body": "## What's Changed\n- fix: something"})
    )
    result = await gh.get_release("owner/lib", "v1.0.1")
    assert "What's Changed" in result["body"]


@respx.mock
async def test_get_file(gh):
    content = base64.b64encode(b"## v1.0.1\n- fix something").decode()
    respx.get("https://api.github.com/repos/owner/lib/contents/CHANGELOG.md").mock(
        return_value=httpx.Response(200, json={"content": content + "\n", "encoding": "base64"})
    )
    result = await gh.get_file("owner/lib", "CHANGELOG.md")
    assert "fix something" in result
