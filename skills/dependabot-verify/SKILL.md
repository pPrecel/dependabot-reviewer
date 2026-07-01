---
name: dependabot-verify
description: >
  Read-only scan of all open Dependabot PRs where the current user is a requested reviewer.
  Reports the status of each PR without taking any write actions (no approvals, no comments,
  no automerge, no branch updates).
  Invoke with: /dependabot-verify
---

# /dependabot-verify

You are executing the Dependabot PR verification workflow. Work autonomously — do not ask the user for input. Process all PRs and present results at the end. **Take no write actions.**

---

## Workflow

### Step 1: Detect tooling

Detect which GitHub API tool is available. Use the first option that works. No write access is required.

**Detection order:**

1. **Read-only MCP tools** — prefer `mcp__github-ro__*` or `mcp__github-tools-ro__*` if present in the session. These are sufficient for all read operations in this workflow.
2. **Read-write MCP tools** — use if read-only MCP tools are absent (they also support read operations).
3. **`gh` CLI** — run `gh auth status` to confirm login. For `github.tools.sap` use `--hostname github.tools.sap`.
4. **`curl`** — last resort. Use `GITHUB_TOKEN` or `GH_TOKEN` env vars. For `github.tools.sap` use base URL `https://github.tools.sap/api/v3`.

Use only one tool for all subsequent GitHub API calls in this workflow. Never mix tools.

### Step 2: Discover PRs

Fetch all open Dependabot PRs where the current user is a requested reviewer, from both:
- `github.com`
- `github.tools.sap`

Use the same queries as described in the `dependabot-reviewer` agent's "Finding Dependabot PRs" section:

```
is:open is:pr author:app/dependabot review-requested:@me
```

Collect results into two lists (one per host). If a host returns an error or no results, note it and continue.

### Step 3: Classify each PR

For each PR, fetch the following data (read-only):

**Via `gh` CLI:**
```bash
gh pr view <number> --repo <owner/repo> \
  --json reviews,statusCheckRollup,autoMergeRequest,mergeStateStatus,comments
```

**Via MCP tools:** Use `pull_request_read` with methods `get_reviews`, `get_check_runs`, `get_status`, `get`, `get_comments` separately as needed. Use `get_check_runs` as the primary method for individual CI check states; `get_status` provides the combined commit status as a fallback.

For each check in `statusCheckRollup` that has `state == WAITING`, also fetch pending deployments:
```bash
gh api /repos/<owner/repo>/actions/runs/<run_id>/pending_deployments
```

Note: Pending deployment detection requires `gh` CLI or `curl` — there is no MCP equivalent. If using MCP tools exclusively, skip the `WAITING FOR ENV` classification and record the check as `⏳ WAITING FOR CI` instead.

**Classification priority (first matching condition wins):**

| Priority | Status | Condition |
|----------|--------|-----------|
| 1 | ⚠️ `ACTION REQUIRED` | Any CI check has `state == FAILURE` or `state == ERROR`, OR any PR comment contains the text "requires manual action ⚠️" |
| 2 | 🔐 `WAITING FOR ENV` | At least one check has `state == WAITING` AND fetching its pending deployments returns a non-empty list |
| 3 | 🔄 `NEEDS BRANCH UPDATE` | `mergeStateStatus == "BEHIND"` |
| 4 | ⏳ `WAITING FOR CI` | No FAILURE/ERROR checks, not BEHIND, but at least one check has `state == PENDING` or `state == IN_PROGRESS` |
| 5 | 👀 `NEEDS REVIEW` | Current user has no `APPROVED` review AND no PR comment contains "Dependabot PR reviewed ✅" or "requires manual action ⚠️" |
| 6 | ✅ `READY` | Current user has an `APPROVED` review, `autoMergeRequest != null`, all CI checks are `SUCCESS`, and `mergeStateStatus != "BEHIND"` |
| 7 | 👀 `NEEDS REVIEW` | Catch-all: any PR that does not match any condition above |

**Note on comment detection (Priority 1 and 5):** Comments to check are PR-level comments and review comments. On the `gh` CLI path, these are included in `--json comments`. On the MCP path, fetch them via `get_comments` method on `pull_request_read`. Look for comments whose body contains exactly "requires manual action ⚠️" (Priority 1) or "Dependabot PR reviewed ✅" (Priority 5).

**Detail field per status:**
- `⚠️ ACTION REQUIRED` → list failing check names, e.g. `CI: test-unit FAILURE`
- `🔐 WAITING FOR ENV` → environment name from the pending deployment, e.g. `environment: production`
- `🔄 NEEDS BRANCH UPDATE` → `branch is behind <base-branch-name>`
- `⏳ WAITING FOR CI` → count of pending checks, e.g. `3 checks pending`
- `👀 NEEDS REVIEW` → `no review yet`
- `✅ READY` → `—`
- `👀 NEEDS REVIEW` (catch-all) → `needs attention`

If fetching data for a PR fails, record status as `❌ ERROR` and detail as the error message. Continue to the next PR.

### Step 4: Present summary tables

After all PRs are processed, display two tables — one for `github.com`, one for `github.tools.sap`:

#### github.com

| Repo | PR | Status | Detail |
|------|----|--------|--------|
| `org/repo` | [#123](https://github.com/org/repo/pull/123) | ✅ READY | — |
| `org/repo` | [#456](https://github.com/org/repo/pull/456) | ⚠️ ACTION REQUIRED | CI: test-unit FAILURE |
| `org/repo` | [#789](https://github.com/org/repo/pull/789) | ⏳ WAITING FOR CI | 3 checks pending |
| `org/repo` | [#101](https://github.com/org/repo/pull/101) | 🔐 WAITING FOR ENV | environment: production |
| `org/repo` | [#102](https://github.com/org/repo/pull/102) | 🔄 NEEDS BRANCH UPDATE | branch is behind main |
| `org/repo` | [#103](https://github.com/org/repo/pull/103) | 👀 NEEDS REVIEW | no review yet |

#### github.tools.sap

_(same format)_

If no PRs were found on either host, say so explicitly:
`No open Dependabot PRs awaiting review on [host].`

**Status legend:**
- `✅ READY` — approved, automerge set, all CI green, branch up to date
- `⚠️ ACTION REQUIRED` — failing CI or prior analysis flagged manual action
- `🔐 WAITING FOR ENV` — pending environment deployment requires your approval
- `🔄 NEEDS BRANCH UPDATE` — branch is behind base, needs update before merge
- `⏳ WAITING FOR CI` — checks still running, no action needed yet
- `👀 NEEDS REVIEW` — PR has not been reviewed or analysed yet
- `❌ ERROR` — failed to fetch PR data; see detail for error message
