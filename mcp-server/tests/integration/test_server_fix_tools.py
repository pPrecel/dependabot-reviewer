import pytest
import respx
import httpx
import base64
from dependabot_mcp.server import get_check_logs, commit_files, post_pr_comment, get_raw_diff, get_file_contents, get_pr_head_sha


@respx.mock
async def test_get_check_logs_returns_file_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPENDABOT_FIX_LOG_DIR", str(tmp_path))
    # check-run details → job_id
    respx.get("https://api.github.com/repos/owner/repo/check-runs/555").mock(
        return_value=httpx.Response(200, json={
            "name": "test-unit",
            "details_url": "https://github.com/owner/repo/actions/runs/111/job/555",
        })
    )
    respx.get("https://api.github.com/repos/owner/repo/actions/jobs/555/logs").mock(
        return_value=httpx.Response(302, headers={"location": "https://logs.example.com/555.txt"})
    )
    respx.get("https://logs.example.com/555.txt").mock(
        return_value=httpx.Response(200, text="Step 1\nFAILED: assertion error")
    )
    result = await get_check_logs(host="github.com", token="tok", repo="owner/repo", check_run_id=555)
    assert result["name"] == "test-unit"
    assert result["file_path"].endswith(".txt")


@respx.mock
async def test_commit_files_returns_commit(monkeypatch):
    respx.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(200, json={
            "data": {
                "createCommitOnBranch": {
                    "commit": {
                        "oid": "aabbcc112233",
                        "url": "https://github.com/owner/repo/commit/aabbcc112233",
                    }
                }
            }
        })
    )
    result = await commit_files(
        host="github.com",
        token="tok",
        repo="owner/repo",
        branch="dependabot/go/foo-2.0.0",
        files=[{"path": "go.mod", "content": "module github.com/owner/repo\n"}],
        message="fix: resolve merge conflicts [dependabot skip]",
        head_sha="abc123",
    )
    assert result["commit_sha"] == "aabbcc112233"


@respx.mock
async def test_post_comment_returns_url():
    respx.post("https://api.github.com/repos/owner/repo/issues/42/comments").mock(
        return_value=httpx.Response(201, json={
            "html_url": "https://github.com/owner/repo/issues/42#issuecomment-999"
        })
    )
    result = await post_pr_comment(host="github.com", token="tok", repo="owner/repo", pr_number=42, body="Automatic fix applied ✅")
    assert "issuecomment" in result["comment_url"]


@respx.mock
async def test_get_raw_diff_returns_text():
    respx.get("https://api.github.com/repos/owner/repo/pulls/42").mock(
        return_value=httpx.Response(200, text="diff --git a/go.mod b/go.mod\n+github.com/foo/bar v2.0.0")
    )
    result = await get_raw_diff(host="github.com", token="tok", repo="owner/repo", pr_number=42)
    assert "go.mod" in result


@respx.mock
async def test_get_file_contents_returns_decoded():
    content = "module github.com/owner/repo\n\ngo 1.21\n"
    encoded = base64.b64encode(content.encode()).decode()
    respx.get("https://api.github.com/repos/owner/repo/contents/go.mod").mock(
        return_value=httpx.Response(200, json={
            "content": encoded + "\n",
            "sha": "deadbeef",
            "encoding": "base64",
        })
    )
    result = await get_file_contents(host="github.com", token="tok", repo="owner/repo", path="go.mod", ref="main")
    assert "go 1.21" in result["content"]
    assert result["sha"] == "deadbeef"


@respx.mock
async def test_get_pr_head_sha_returns_sha():
    respx.get("https://api.github.com/repos/owner/repo/pulls/42").mock(
        return_value=httpx.Response(200, json={
            "number": 42,
            "head": {"sha": "abc123def456", "ref": "dependabot/go/foo-2.0.0"},
            "base": {"ref": "main"},
            "mergeable_state": "behind",
        })
    )
    result = await get_pr_head_sha(host="github.com", token="tok", repo="owner/repo", pr_number=42)
    assert result == "abc123def456"


@respx.mock
async def test_get_pr_head_sha_raises_on_missing_sha():
    respx.get("https://api.github.com/repos/owner/repo/pulls/99").mock(
        return_value=httpx.Response(200, json={
            "number": 99,
            "head": {},
            "base": {"ref": "main"},
            "mergeable_state": "unknown",
        })
    )
    try:
        await get_pr_head_sha(host="github.com", token="tok", repo="owner/repo", pr_number=99)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "no head SHA" in str(e)
