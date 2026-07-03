# Main Branch Health Check — Design

**Date:** 2026-07-03
**Scope:** `dependabot-verify` skill + MCP server

---

## Overview

Extend `dependabot-verify` to check whether the main branch of every monitored repository is healthy after recent Dependabot merges. The feature adds a new "Main branch health" section at the end of the verify report, showing the current CI status of each repo's default branch.

No changes to `dependabot-fix` or `dependabot-review` in this scope.

---

## Components

### 1. New MCP tool: `get_branch_ci_status`

**File:** `mcp-server/dependabot_mcp/server.py` + `github_client.py`

```python
get_branch_ci_status(host: str, token: str, repo: str, branch: str) -> dict
```

**Returns:**
```json
{
  "sha": "<HEAD commit SHA>",
  "branch": "main",
  "ci_status": "passing" | "failing" | "pending" | "unknown",
  "failing_checks": [{"name": "...", "conclusion": "..."}],
  "total_checks": 5,
  "passing_checks": 4
}
```

**Implementation:**
1. `GET /repos/{repo}/git/ref/heads/{branch}` — resolve HEAD SHA for the branch
2. Call existing `list_check_runs(repo, head_sha)` — fetch all check runs for that SHA
3. Classify `ci_status` using the same logic as `get_pr_details`:
   - Any check with `conclusion == "failure"` or `"timed_out"` → `"failing"`
   - Any check with `status == "in_progress"` or `"queued"` → `"pending"` (if no failures)
   - All checks `conclusion == "success"` → `"passing"`
   - No checks found → `"unknown"`
4. `failing_checks` — list of `{name, conclusion}` for checks where conclusion is failure/timed_out

**Error handling:** If the branch ref returns 404, raise a clear error (caller will fall back to `"master"`).

---

### 2. New MCP tool: `list_recently_merged_dependabot_prs`

**File:** `mcp-server/dependabot_mcp/server.py`

```python
list_recently_merged_dependabot_prs(host: str, token: str, since: str) -> list[dict]
```

- `since`: ISO 8601 date string, e.g. `"2026-06-26"` (7 days ago)
- Uses existing `search_prs` with query: `is:pr is:merged author:app/dependabot merged:>={since} reviewed-by:@me` (github.com) or `author:dependabot` (GHES)
- Returns same shape as `list_dependabot_prs`: `[{number, repo, title, url}]`
- Deduplicates by `(repo, number)`

**Note on Dependabot identity:** same rule as `list_dependabot_prs` — `app/dependabot` on github.com, `dependabot` on GHES.

---

### 3. Changes to `dependabot-verify` skill

**File:** `skills/dependabot-verify/SKILL.md`

Add **Step 5** after the existing Step 4 (summary tables):

#### Step 5: Main branch health

1. Collect unique repos from:
   - All PRs discovered in Step 2 (open PRs)
   - Results of `list_recently_merged_dependabot_prs(host, token, since=<7 days ago ISO date>)` for each host

2. Deduplicate repos (same repo may appear in both lists).

3. For each unique `(host, repo)`:
   - Call `get_branch_ci_status(host, token, repo, branch="main")`
   - If 404 → retry with `branch="master"`
   - If still error → record as `❌ ERROR`

4. Display one table per host:

```
#### Main branch health — <host>

| Repo | Branch | Status | Failing checks |
|------|--------|--------|----------------|
| `org/repo` | main | ✅ passing | — |
| `org/repo` | main | ❌ failing | build, test-unit |
| `org/repo` | main | ⏳ pending | — |
| `org/repo` | main | ❓ unknown | — |
| `org/repo` | main | ❌ ERROR | <error message> |
```

**Status legend:**
- `✅ passing` — all checks green
- `❌ failing` — at least one check red; failing check names listed in "Failing checks" column
- `⏳ pending` — checks still running
- `❓ unknown` — no checks found or state cannot be determined
- `❌ ERROR` — failed to fetch data; see detail

---

## Data flow summary

```
dependabot-verify Step 2 (open PRs)       list_recently_merged_dependabot_prs
        |                                              |
        +-------------------+------------------------+
                            |
                    unique (host, repo) list
                            |
               get_branch_ci_status per repo
                            |
              "Main branch health" table(s)
```

---

## What is NOT in scope

- `dependabot-fix` skill changes
- `dependabot-review` skill changes
- Detecting *which specific merge* caused a regression (compare-before/after approach)
- Alerting or notifications beyond the verify report
- Configurable time window (hardcoded 7 days for merged PR discovery)
