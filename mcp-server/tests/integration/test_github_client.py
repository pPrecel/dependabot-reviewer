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
async def test_post_review(gh):
    respx.post("https://api.github.com/repos/owner/repo/pulls/42/reviews").mock(
        return_value=httpx.Response(200, json={"id": 99, "state": "APPROVED"})
    )
    result = await gh.post_review("owner/repo", 42, "LGTM")
    assert result["state"] == "APPROVED"


@respx.mock
async def test_post_comment(gh):
    respx.post("https://api.github.com/repos/owner/repo/issues/42/comments").mock(
        return_value=httpx.Response(201, json={
            "html_url": "https://github.com/owner/repo/issues/42#issuecomment-1"
        })
    )
    result = await gh.post_comment("owner/repo", 42, "needs action")
    assert "issuecomment" in result["html_url"]


@respx.mock
async def test_update_branch(gh):
    respx.put("https://api.github.com/repos/owner/repo/pulls/42/update-branch").mock(
        return_value=httpx.Response(202, json={"message": "Updating pull request branch."})
    )
    result = await gh.update_branch("owner/repo", 42)
    assert result["message"] == "Updating pull request branch."


@respx.mock
async def test_approve_deployment(gh):
    respx.post(
        "https://api.github.com/repos/owner/repo/actions/runs/123/pending_deployments"
    ).mock(return_value=httpx.Response(200, json=[{"id": 456, "state": "approved"}]))
    result = await gh.approve_deployment("owner/repo", 123, [456])
    assert result[0]["state"] == "approved"
