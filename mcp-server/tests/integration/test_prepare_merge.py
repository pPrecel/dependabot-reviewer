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


@respx.mock
async def test_prepare_merge_approves_env_using_workflow_run_id():
    """Env approval must use workflow run ID from details_url, not check-run ID."""
    CHECK_RUN_ID = 84732422796   # check-run ID (would 404 if used directly)
    WORKFLOW_RUN_ID = 28578401211  # correct workflow run ID from details_url

    respx.get(f"{BASE}/repos/owner/repo/pulls/42").mock(
        return_value=httpx.Response(200, json=_pr_response())
    )
    respx.get(f"{BASE}/repos/owner/repo/commits/abc123/check-runs").mock(
        return_value=httpx.Response(200, json={
            "check_runs": [
                {
                    "id": CHECK_RUN_ID,
                    "name": "select-environment",
                    "status": "waiting",
                    "conclusion": None,
                    "details_url": f"https://github.com/owner/repo/actions/runs/{WORKFLOW_RUN_ID}/job/{CHECK_RUN_ID}",
                }
            ]
        })
    )
    respx.get(f"{BASE}/repos/owner/repo/actions/runs/{WORKFLOW_RUN_ID}/pending_deployments").mock(
        return_value=httpx.Response(200, json=[
            {"id": 15329854523, "current_user_can_approve": True, "environment": {"id": 99, "name": "restricted"}}
        ])
    )
    respx.post(f"{BASE}/repos/owner/repo/actions/runs/{WORKFLOW_RUN_ID}/pending_deployments").mock(
        return_value=httpx.Response(200, json=[])
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
    assert data["envs_approved"] == 1
