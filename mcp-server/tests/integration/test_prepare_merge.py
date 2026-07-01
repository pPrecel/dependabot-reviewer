import pytest
import respx
import httpx
import json
from dependabot_mcp.server import mcp


BASE = "https://api.github.com"


def _pr_response(mergeable_state: str = "clean", auto_merge=None, node_id: str = "PR_1") -> dict:
    return {
        "number": 42,
        "node_id": node_id,
        "title": "bump foo from 1.0.0 to 1.0.1",
        "head": {"sha": "abc123"},
        "auto_merge": auto_merge,
        "mergeable_state": mergeable_state,
    }


def _checks_response(conclusion: str = "success") -> dict:
    return {
        "check_runs": [
            {"name": "ci", "status": "completed", "conclusion": conclusion}
        ]
    }


@respx.mock
async def test_prepare_merge_dirty_returns_needs_manual_rebase():
    respx.get(f"{BASE}/repos/owner/repo/pulls/42").mock(
        return_value=httpx.Response(200, json=_pr_response(mergeable_state="dirty"))
    )
    result = await mcp.call_tool("prepare_merge", {
        "host": "github.com", "token": "tok",
        "repo": "owner/repo", "pr_number": 42,
        "comment": "LGTM",
    })
    data = json.loads(result[0].text)
    assert data["status"] == "needs_manual_rebase"


@respx.mock
async def test_prepare_merge_behind_updates_branch():
    pr_behind = _pr_response(mergeable_state="behind")
    pr_clean = _pr_response(mergeable_state="clean")
    call_count = 0

    def pr_side_effect(request):
        nonlocal call_count
        call_count += 1
        # First call: behind; second call (after update): clean
        return httpx.Response(200, json=pr_behind if call_count == 1 else pr_clean)

    respx.get(f"{BASE}/repos/owner/repo/pulls/42").mock(side_effect=pr_side_effect)
    respx.put(f"{BASE}/repos/owner/repo/pulls/42/update-branch").mock(
        return_value=httpx.Response(202, json={"message": "Updating pull request branch."})
    )
    respx.get(f"{BASE}/repos/owner/repo/commits/abc123/check-runs").mock(
        return_value=httpx.Response(200, json=_checks_response())
    )
    respx.post(f"{BASE}/graphql").mock(
        return_value=httpx.Response(200, json={"data": {"enablePullRequestAutoMerge": {}}})
    )
    respx.get(f"{BASE}/repos/owner/repo/pulls/42/reviews").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{BASE}/user").mock(
        return_value=httpx.Response(200, json={"login": "testuser"})
    )
    respx.post(f"{BASE}/repos/owner/repo/pulls/42/reviews").mock(
        return_value=httpx.Response(200, json={"id": 1, "state": "APPROVED"})
    )

    result = await mcp.call_tool("prepare_merge", {
        "host": "github.com", "token": "tok",
        "repo": "owner/repo", "pr_number": 42,
        "comment": "LGTM",
    })
    data = json.loads(result[0].text)
    assert data["status"] == "done"
    assert data["branch_updated"] is True


@respx.mock
async def test_prepare_merge_done_clean():
    respx.get(f"{BASE}/repos/owner/repo/pulls/42").mock(
        return_value=httpx.Response(200, json=_pr_response())
    )
    respx.get(f"{BASE}/repos/owner/repo/commits/abc123/check-runs").mock(
        return_value=httpx.Response(200, json=_checks_response())
    )
    respx.post(f"{BASE}/graphql").mock(
        return_value=httpx.Response(200, json={"data": {"enablePullRequestAutoMerge": {}}})
    )
    respx.get(f"{BASE}/repos/owner/repo/pulls/42/reviews").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{BASE}/user").mock(
        return_value=httpx.Response(200, json={"login": "testuser"})
    )
    respx.post(f"{BASE}/repos/owner/repo/pulls/42/reviews").mock(
        return_value=httpx.Response(200, json={"id": 1, "state": "APPROVED"})
    )
    result = await mcp.call_tool("prepare_merge", {
        "host": "github.com", "token": "tok",
        "repo": "owner/repo", "pr_number": 42,
        "comment": "LGTM",
    })
    data = json.loads(result[0].text)
    assert data["status"] == "done"
    assert data["approved"] is True
    assert data["automerge_set"] is True


@respx.mock
async def test_prepare_merge_skips_approve_if_already_approved():
    respx.get(f"{BASE}/repos/owner/repo/pulls/42").mock(
        return_value=httpx.Response(200, json=_pr_response(auto_merge={"merge_method": "squash"}))
    )
    respx.get(f"{BASE}/repos/owner/repo/commits/abc123/check-runs").mock(
        return_value=httpx.Response(200, json=_checks_response())
    )
    respx.get(f"{BASE}/repos/owner/repo/pulls/42/reviews").mock(
        return_value=httpx.Response(200, json=[{"user": {"login": "pPrecel"}, "state": "APPROVED"}])
    )
    respx.get(f"{BASE}/user").mock(
        return_value=httpx.Response(200, json={"login": "pPrecel"})
    )

    result = await mcp.call_tool("prepare_merge", {
        "host": "github.com", "token": "tok",
        "repo": "owner/repo", "pr_number": 42,
        "comment": "LGTM",
    })
    data = json.loads(result[0].text)
    assert data["status"] == "done"
    assert data["approved"] is False   # already approved, not re-approved
    assert data["automerge_set"] is False  # already set, not re-set
