import pytest
import respx
import httpx
from dependabot_mcp.server import get_branch_ci_status, list_recently_merged_dependabot_prs


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


@respx.mock
async def test_list_recently_merged_dependabot_prs_github_com():
    respx.get("https://api.github.com/search/issues").mock(
        return_value=httpx.Response(200, json={
            "items": [
                {
                    "number": 101,
                    "repository_url": "https://api.github.com/repos/owner/repo",
                    "title": "bump foo from 1.0.0 to 1.1.0",
                    "html_url": "https://github.com/owner/repo/pull/101",
                },
                {
                    "number": 102,
                    "repository_url": "https://api.github.com/repos/owner/repo",
                    "title": "bump bar from 2.0.0 to 2.0.1",
                    "html_url": "https://github.com/owner/repo/pull/102",
                },
            ]
        })
    )
    result = await list_recently_merged_dependabot_prs(
        host="github.com", token="tok", since="2026-06-26"
    )
    assert len(result) == 2
    assert result[0]["number"] == 101
    assert result[0]["repo"] == "owner/repo"
    assert result[1]["number"] == 102


@respx.mock
async def test_list_recently_merged_dependabot_prs_deduplicates():
    # Same PR returned by multiple queries (e.g. reviewed-by + review-requested)
    respx.get("https://api.github.com/search/issues").mock(
        side_effect=[
            httpx.Response(200, json={
                "items": [
                    {
                        "number": 55,
                        "repository_url": "https://api.github.com/repos/org/proj",
                        "title": "bump lib",
                        "html_url": "https://github.com/org/proj/pull/55",
                    }
                ]
            }),
            httpx.Response(200, json={
                "items": [
                    {
                        "number": 55,
                        "repository_url": "https://api.github.com/repos/org/proj",
                        "title": "bump lib",
                        "html_url": "https://github.com/org/proj/pull/55",
                    }
                ]
            }),
        ]
    )
    result = await list_recently_merged_dependabot_prs(
        host="github.com", token="tok", since="2026-06-26"
    )
    assert len(result) == 1
    assert result[0]["number"] == 55


@respx.mock
async def test_list_recently_merged_dependabot_prs_ghes_uses_plain_author():
    """On GHES (non-github.com host), query should use author:dependabot, not author:app/dependabot."""
    captured_queries = []

    def capture(request):
        captured_queries.append(request.url.params.get("q", ""))
        return httpx.Response(200, json={"items": []})

    respx.get("https://github.tools.sap/api/v3/search/issues").mock(side_effect=capture)

    await list_recently_merged_dependabot_prs(
        host="github.tools.sap", token="tok", since="2026-06-26"
    )
    # All queries should use author:dependabot (plain), not author:app/dependabot
    assert all("author:app/" not in q for q in captured_queries)
    assert any("author:dependabot" in q for q in captured_queries)


@respx.mock
async def test_list_dependabot_prs_with_org_filter():
    """org= adds org:<org> qualifier to all search queries."""
    captured_queries = []

    def capture(request):
        captured_queries.append(request.url.params.get("q", ""))
        return httpx.Response(200, json={"items": []})

    respx.get("https://api.github.com/search/issues").mock(side_effect=capture)

    from dependabot_mcp.server import list_dependabot_prs
    await list_dependabot_prs(host="github.com", token="tok", org="myorg")

    assert all("org:myorg" in q for q in captured_queries)
    assert all("repo:" not in q for q in captured_queries)


@respx.mock
async def test_list_dependabot_prs_with_repo_filter():
    """repo= adds repo:<org>/<repo> qualifier and takes precedence over org=."""
    captured_queries = []

    def capture(request):
        captured_queries.append(request.url.params.get("q", ""))
        return httpx.Response(200, json={"items": []})

    respx.get("https://api.github.com/search/issues").mock(side_effect=capture)

    from dependabot_mcp.server import list_dependabot_prs
    await list_dependabot_prs(host="github.com", token="tok", org="myorg", repo="myorg/myrepo")

    assert all("repo:myorg/myrepo" in q for q in captured_queries)
    assert all("org:myorg" not in q for q in captured_queries)


@respx.mock
async def test_list_dependabot_prs_no_filter_unchanged():
    """Without org or repo, queries are unchanged from before."""
    captured_queries = []

    def capture(request):
        captured_queries.append(request.url.params.get("q", ""))
        return httpx.Response(200, json={"items": []})

    respx.get("https://api.github.com/search/issues").mock(side_effect=capture)

    from dependabot_mcp.server import list_dependabot_prs
    await list_dependabot_prs(host="github.com", token="tok")

    assert all("org:" not in q for q in captured_queries)
    assert all("repo:" not in q for q in captured_queries)
    # All queries include standard Dependabot author qualifiers
    assert any("author:app/dependabot" in q for q in captured_queries)
