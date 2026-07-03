# Main Branch Health Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Main branch health" section to `dependabot-verify` that shows CI status of each monitored repo's default branch.

**Architecture:** Two new MCP tools (`get_branch_ci_status`, `list_recently_merged_dependabot_prs`) added to the Python MCP server. The `dependabot-verify` skill gains a new Step 5 that collects unique repos from open + recently merged PRs, calls `get_branch_ci_status` for each, and renders a health table.

**Tech Stack:** Python 3.11+, httpx, pydantic, pytest + respx for mocking, FastMCP

---

## File map

| File | Change |
|------|--------|
| `mcp-server/dependabot_mcp/models.py` | Add `BranchCiStatus` model |
| `mcp-server/dependabot_mcp/github_client.py` | Add `get_branch_head_sha()` method |
| `mcp-server/dependabot_mcp/server.py` | Add `get_branch_ci_status` and `list_recently_merged_dependabot_prs` tools |
| `mcp-server/tests/unit/test_models.py` | Add `BranchCiStatus` model test |
| `mcp-server/tests/integration/test_github_client.py` | Add `get_branch_head_sha` test |
| `mcp-server/tests/integration/test_server_health_tools.py` | New file — integration tests for the two new tools |
| `skills/dependabot-verify/SKILL.md` | Add Step 5 + update agent tool table |
| `agents/dependabot-reviewer.md` | Update tool table with the two new tools |

---

## Task 1: Add `BranchCiStatus` model

**Files:**
- Modify: `mcp-server/dependabot_mcp/models.py`
- Test: `mcp-server/tests/unit/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `mcp-server/tests/unit/test_models.py`:

```python
from dependabot_mcp.models import BranchCiStatus

def test_branch_ci_status_fields():
    result = BranchCiStatus(
        sha="abc123",
        branch="main",
        ci_status="failing",
        failing_checks=[{"name": "build", "conclusion": "failure"}],
        total_checks=3,
        passing_checks=2,
    )
    assert result.sha == "abc123"
    assert result.ci_status == "failing"
    assert result.total_checks == 3
    assert result.passing_checks == 2
    assert result.failing_checks[0]["name"] == "build"


def test_branch_ci_status_passing():
    result = BranchCiStatus(
        sha="def456",
        branch="main",
        ci_status="passing",
        failing_checks=[],
        total_checks=5,
        passing_checks=5,
    )
    assert result.failing_checks == []
    assert result.passing_checks == 5


def test_branch_ci_status_unknown():
    result = BranchCiStatus(
        sha="",
        branch="main",
        ci_status="unknown",
        failing_checks=[],
        total_checks=0,
        passing_checks=0,
    )
    assert result.ci_status == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mcp-server && .venv/bin/pytest tests/unit/test_models.py -v -k "branch_ci"
```

Expected: `ImportError: cannot import name 'BranchCiStatus'`

- [ ] **Step 3: Add `BranchCiStatus` to models.py**

Add at the end of `mcp-server/dependabot_mcp/models.py`:

```python
class BranchCiStatus(BaseModel):
    sha: str
    branch: str
    ci_status: Literal["passing", "failing", "pending", "unknown"]
    failing_checks: list[dict]   # [{name: str, conclusion: str}]
    total_checks: int
    passing_checks: int
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd mcp-server && .venv/bin/pytest tests/unit/test_models.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd mcp-server && git add dependabot_mcp/models.py tests/unit/test_models.py
git commit -m "feat: add BranchCiStatus model"
```

---

## Task 2: Add `get_branch_head_sha` to `GithubClient`

**Files:**
- Modify: `mcp-server/dependabot_mcp/github_client.py`
- Test: `mcp-server/tests/integration/test_github_client.py`

- [ ] **Step 1: Write the failing test**

Add to `mcp-server/tests/integration/test_github_client.py`:

```python
@respx.mock
async def test_get_branch_head_sha(gh):
    respx.get("https://api.github.com/repos/owner/repo/git/ref/heads/main").mock(
        return_value=httpx.Response(200, json={
            "ref": "refs/heads/main",
            "object": {"sha": "deadbeef1234", "type": "commit"},
        })
    )
    sha = await gh.get_branch_head_sha("owner/repo", "main")
    assert sha == "deadbeef1234"


@respx.mock
async def test_get_branch_head_sha_not_found(gh):
    respx.get("https://api.github.com/repos/owner/repo/git/ref/heads/nonexistent").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        await gh.get_branch_head_sha("owner/repo", "nonexistent")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mcp-server && .venv/bin/pytest tests/integration/test_github_client.py -v -k "branch_head_sha"
```

Expected: `AttributeError: 'GithubClient' object has no attribute 'get_branch_head_sha'`

- [ ] **Step 3: Add `get_branch_head_sha` method to `github_client.py`**

Add inside `GithubClient` class, after the `list_check_runs` method (line 116), before the `# ── Write ──` comment:

```python
    async def get_branch_head_sha(self, repo: str, branch: str) -> str:
        """Fetch HEAD commit SHA for a branch. Raises HTTPStatusError on 404."""
        r = await self._client.get(f"/repos/{repo}/git/ref/heads/{branch}")
        r.raise_for_status()
        return r.json()["object"]["sha"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd mcp-server && .venv/bin/pytest tests/integration/test_github_client.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp-server/dependabot_mcp/github_client.py mcp-server/tests/integration/test_github_client.py
git commit -m "feat: add get_branch_head_sha to GithubClient"
```

---

## Task 3: Add `get_branch_ci_status` MCP tool

**Files:**
- Modify: `mcp-server/dependabot_mcp/server.py`
- Create: `mcp-server/tests/integration/test_server_health_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `mcp-server/tests/integration/test_server_health_tools.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd mcp-server && .venv/bin/pytest tests/integration/test_server_health_tools.py -v
```

Expected: `ImportError: cannot import name 'get_branch_ci_status' from 'dependabot_mcp.server'`

- [ ] **Step 3: Add `get_branch_ci_status` to `server.py`**

Add the import at the top of `server.py` — update the `from .models import (...)` block to include `BranchCiStatus`:

```python
from .models import (
    PRSummary, Review, CheckResult, DiffClassification,
    PRDetails, Comment, PrepareMergeResult, CommentResult,
    CheckLog, CommitResult, BranchCiStatus,
)
```

Add the new tool at the end of `server.py` (before the last blank line):

```python
@mcp.tool()
async def get_branch_ci_status(host: str, token: str, repo: str, branch: str) -> dict:
    """
    Get CI status of the HEAD commit of a branch.
    Returns {sha, branch, ci_status, failing_checks, total_checks, passing_checks}.
    ci_status: "passing" | "failing" | "pending" | "unknown"
    Raises HTTPStatusError if the branch does not exist (e.g. 404).
    """
    client = GithubClient(host, token)
    sha = await client.get_branch_head_sha(repo, branch)
    checks = await client.list_check_runs(repo, sha)

    if not checks:
        return BranchCiStatus(
            sha=sha, branch=branch, ci_status="unknown",
            failing_checks=[], total_checks=0, passing_checks=0,
        ).model_dump()

    failing = [
        {"name": c["name"], "conclusion": c.get("conclusion", "")}
        for c in checks
        if c.get("conclusion") in ("failure", "timed_out")
    ]
    pending = any(
        c.get("status") in ("in_progress", "queued") or c.get("conclusion") is None
        for c in checks
    )
    passing_count = sum(1 for c in checks if c.get("conclusion") == "success")

    if failing:
        ci_status = "failing"
    elif pending:
        ci_status = "pending"
    else:
        ci_status = "passing"

    return BranchCiStatus(
        sha=sha,
        branch=branch,
        ci_status=ci_status,
        failing_checks=failing,
        total_checks=len(checks),
        passing_checks=passing_count,
    ).model_dump()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd mcp-server && .venv/bin/pytest tests/integration/test_server_health_tools.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Run full test suite to check nothing is broken**

```bash
cd mcp-server && .venv/bin/pytest -v
```

Expected: all existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add mcp-server/dependabot_mcp/server.py mcp-server/dependabot_mcp/models.py mcp-server/tests/integration/test_server_health_tools.py
git commit -m "feat: add get_branch_ci_status MCP tool"
```

---

## Task 4: Add `list_recently_merged_dependabot_prs` MCP tool

**Files:**
- Modify: `mcp-server/dependabot_mcp/server.py`
- Modify: `mcp-server/tests/integration/test_server_health_tools.py`

- [ ] **Step 1: Write the failing tests**

Add to `mcp-server/tests/integration/test_server_health_tools.py`:

```python
from dependabot_mcp.server import get_branch_ci_status, list_recently_merged_dependabot_prs


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd mcp-server && .venv/bin/pytest tests/integration/test_server_health_tools.py -v -k "merged"
```

Expected: `ImportError: cannot import name 'list_recently_merged_dependabot_prs'`

- [ ] **Step 3: Add `list_recently_merged_dependabot_prs` to `server.py`**

Add after the `get_branch_ci_status` tool in `server.py`:

```python
@mcp.tool()
async def list_recently_merged_dependabot_prs(host: str, token: str, since: str) -> list[dict]:
    """
    List Dependabot PRs merged since `since` (ISO 8601 date, e.g. "2026-06-26")
    where the authenticated user reviewed the PR.
    Returns: list of {number, repo, title, url}
    """
    client = GithubClient(host, token)
    # On github.com Dependabot is a GitHub App; on GHES it's a plain user
    authors = (
        ["app/dependabot", "app/ospo-renovate"]
        if host == "github.com"
        else ["dependabot", "ospo-renovate"]
    )
    queries = [
        f"is:pr is:merged author:{author} merged:>={since} reviewed-by:@me"
        for author in authors
    ]
    results = await asyncio.gather(*[client.search_prs(q) for q in queries], return_exceptions=True)
    merged = []
    for items in results:
        if isinstance(items, Exception):
            continue
        for item in items:
            repo = _repo_from_url(item.get("repository_url", ""))
            merged.append({
                "number": item["number"],
                "repo": repo,
                "title": item["title"],
                "url": item["html_url"],
            })
    return _deduplicate(merged)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd mcp-server && .venv/bin/pytest tests/integration/test_server_health_tools.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd mcp-server && .venv/bin/pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add mcp-server/dependabot_mcp/server.py mcp-server/tests/integration/test_server_health_tools.py
git commit -m "feat: add list_recently_merged_dependabot_prs MCP tool"
```

---

## Task 5: Update `dependabot-verify` skill with Step 5

**Files:**
- Modify: `skills/dependabot-verify/SKILL.md`

- [ ] **Step 1: Add Step 5 to the skill**

Open `skills/dependabot-verify/SKILL.md`. After the existing `### Step 4: Present summary tables` section (which ends with the status legend), append:

```markdown
---

### Step 5: Main branch health

After presenting the PR status tables, check the CI health of the default branch for each monitored repository.

**Step 5a — Collect unique repos:**

1. From Step 2: collect all `repo` values from the open PR list (already in memory).
2. For each host, call:
   ```
   list_recently_merged_dependabot_prs(host=<host>, token=<token>, since=<ISO date 7 days ago>)
   ```
   Compute `since` as today's date minus 7 days in `YYYY-MM-DD` format (e.g. if today is `2026-07-03`, use `since="2026-06-26"`).
3. Add all `repo` values from the merged PRs list.
4. Deduplicate: collect a set of unique `repo` strings per host.

**Step 5b — Check each repo's default branch:**

For each unique `(host, repo)`:
1. Call `get_branch_ci_status(host, token, repo, branch="main")`.
2. If the call returns a 404 error → retry with `branch="master"`.
3. If both fail → record status as `❌ ERROR` with the error message.

**Step 5c — Display health table:**

Display one table per host below the PR status tables:

```
#### Main branch health — <host>

| Repo | Branch | Status | Failing checks |
|------|--------|--------|----------------|
| `org/repo` | main | ✅ passing | — |
| `org/repo` | main | ❌ failing | build, lint |
| `org/repo` | main | ⏳ pending | — |
| `org/repo` | main | ❓ unknown | — |
| `org/repo` | main | ❌ ERROR | <error message> |
```

Map `ci_status` from `get_branch_ci_status` to display status:
- `"passing"` → `✅ passing`
- `"failing"` → `❌ failing` (list `failing_checks[].name` comma-separated in "Failing checks" column)
- `"pending"` → `⏳ pending`
- `"unknown"` → `❓ unknown`
- error → `❌ ERROR`

If no repos were found for a host: `No repositories to check on <host>.`
```

- [ ] **Step 2: Verify the skill file is well-formed**

Read the full file and check that:
- Step 5 appears after Step 4
- The markdown table inside the code block is not broken
- No stray backticks or unclosed code fences

```bash
grep -n "### Step" skills/dependabot-verify/SKILL.md
```

Expected output includes lines for Step 1, Step 1.5, Step 2, Step 3, Step 4, and Step 5.

- [ ] **Step 3: Commit**

```bash
git add skills/dependabot-verify/SKILL.md
git commit -m "feat: add main branch health check to dependabot-verify (Step 5)"
```

---

## Task 6: Update agent tool table

**Files:**
- Modify: `agents/dependabot-reviewer.md`

- [ ] **Step 1: Add the two new tools to the tool table**

In `agents/dependabot-reviewer.md`, find the `## Plugin MCP Server` section and the tools table. Add two rows after the existing `post_action_required_comment` row:

```markdown
| `get_branch_ci_status(host, token, repo, branch)` | Get CI status of the HEAD commit of a branch. Returns `{sha, branch, ci_status, failing_checks, total_checks, passing_checks}`. `ci_status`: `"passing"` \| `"failing"` \| `"pending"` \| `"unknown"`. Raises on 404. |
| `list_recently_merged_dependabot_prs(host, token, since)` | List Dependabot/ospo-renovate PRs merged since `since` (ISO 8601 date) that the current user reviewed. Returns `[{number, repo, title, url}]`. |
```

- [ ] **Step 2: Commit**

```bash
git add agents/dependabot-reviewer.md
git commit -m "docs: update agent tool table with new health check tools"
```

---

## Self-review

**Spec coverage:**
- ✅ `get_branch_ci_status` tool — Task 3
- ✅ `list_recently_merged_dependabot_prs` tool — Task 4
- ✅ `BranchCiStatus` model — Task 1
- ✅ `get_branch_head_sha` in `GithubClient` — Task 2
- ✅ `dependabot-verify` Step 5 — Task 5
- ✅ Agent tool table updated — Task 6
- ✅ GHES vs github.com author qualifier — Task 4 Step 3 + test
- ✅ main → master fallback — Task 5 Step 1 (skill prose)
- ✅ 7-day window hardcoded — Task 5 Step 1
- ✅ Deduplication of repos — Task 5 Step 1a

**Placeholder scan:** None found — all steps contain actual code.

**Type consistency:**
- `BranchCiStatus.failing_checks` is `list[dict]` throughout (Tasks 1, 3)
- `get_branch_head_sha` returns `str` — used as `sha` in Task 3
- `list_recently_merged_dependabot_prs` returns `list[dict]` with same shape as `list_dependabot_prs` — used by skill in Task 5
- `_deduplicate` and `_repo_from_url` are existing helpers reused in Task 4 ✅
