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

All GitHub I/O is performed through the `dependabot-reviewer` MCP server tools. If the MCP server is not present in the session or returns an error, stop and report the error — do not fall back to `gh` CLI or `curl`.

---

## Workflow

### Step 1: Acquire tokens

```bash
TOKEN_GH=$(gh auth token)
TOKEN_SAP=$(GH_HOST=github.tools.sap gh auth token 2>/dev/null || echo "")
```

If `TOKEN_SAP` is empty, skip `github.tools.sap` processing and note it in the summary.

---

### Step 2: Discover PRs

For each host that has a token, call:

```
list_dependabot_prs(host="github.com", token=TOKEN_GH)
list_dependabot_prs(host="github.tools.sap", token=TOKEN_SAP)   # if token available
```

For `github.com`, also fetch all Dependabot PRs in the `kyma-project` org. The `list_dependabot_prs` tool does not cover the org-wide query — run it via `gh` CLI and merge results:

```bash
gh search prs --author app/dependabot --owner kyma-project --state open \
  --json number,title,url,repository --limit 100
```

Collect results into two lists (one per host), deduplicated by PR number. If a host returns an error, record the error and continue with the other host.

---

### Step 3: Classify each PR

For each PR call:

```
get_pr_details(host, token, repo=pr.repo, pr_number=pr.number)
```

The returned `PRDetails` contains all fields needed for classification:
- `reviews` — list of `{author, state}` (check for `state == "APPROVED"` from current user)
- `auto_merge_set` — boolean
- `ci_status` — `"passing"` | `"failing"` | `"pending"`
- `failing_checks` — list of `{name, state}`
- `merge_state` — `"clean"` | `"behind"` | `"dirty"` | `"unknown"`
- `comments` — list of `{author, body, created_at}`

Note: `get_pr_details` does not detect pending environment deployments. The `🔐 WAITING FOR ENV` status is not available on the MCP server path — skip it.

**Classification priority (first matching condition wins):**

| Priority | Status | Condition |
|----------|--------|-----------|
| 1 | ⚠️ `ACTION REQUIRED` | `ci_status == "failing"`, OR any comment body contains `"requires manual action ⚠️"` |
| 2 | 🔄 `NEEDS BRANCH UPDATE` | `merge_state == "behind"` |
| 3 | ⏳ `WAITING FOR CI` | `ci_status == "pending"` |
| 4 | 👀 `NEEDS REVIEW` | No `APPROVED` review from current user AND no comment contains `"Dependabot PR reviewed ✅"` or `"requires manual action ⚠️"` |
| 5 | ✅ `READY` | `APPROVED` review from current user, `auto_merge_set == true`, `ci_status == "passing"`, `merge_state != "behind"` |
| 6 | 👀 `NEEDS REVIEW` | Catch-all |

**Detail field per status:**
- `⚠️ ACTION REQUIRED` → list failing check names, e.g. `CI: test-unit FAILURE`
- `🔄 NEEDS BRANCH UPDATE` → `branch is behind <base-branch-name>`
- `⏳ WAITING FOR CI` → count of pending checks, e.g. `3 checks pending`
- `👀 NEEDS REVIEW` → `no review yet`
- `✅ READY` → `—`
- `👀 NEEDS REVIEW` (catch-all) → `needs attention`

If fetching data for a PR fails, record status as `❌ ERROR` and detail as the error message. Continue to the next PR.

---

### Step 4: Present summary tables

After all PRs are processed, display two tables — one for `github.com`, one for `github.tools.sap`:

#### github.com

| Repo | PR | Status | Detail |
|------|----|--------|--------|
| `org/repo` | [#123](https://github.com/org/repo/pull/123) | ✅ READY | — |
| `org/repo` | [#456](https://github.com/org/repo/pull/456) | ⚠️ ACTION REQUIRED | CI: test-unit FAILURE |
| `org/repo` | [#789](https://github.com/org/repo/pull/789) | ⏳ WAITING FOR CI | 3 checks pending |
| `org/repo` | [#102](https://github.com/org/repo/pull/102) | 🔄 NEEDS BRANCH UPDATE | branch is behind main |
| `org/repo` | [#103](https://github.com/org/repo/pull/103) | 👀 NEEDS REVIEW | no review yet |

#### github.tools.sap

_(same format)_

If no PRs were found on either host, say so explicitly:
`No open Dependabot PRs awaiting review on [host].`

**Status legend:**
- `✅ READY` — approved, automerge set, all CI green, branch up to date
- `⚠️ ACTION REQUIRED` — failing CI or prior analysis flagged manual action
- `🔄 NEEDS BRANCH UPDATE` — branch is behind base, needs update before merge
- `⏳ WAITING FOR CI` — checks still running, no action needed yet
- `👀 NEEDS REVIEW` — PR has not been reviewed or analysed yet
- `❌ ERROR` — failed to fetch PR data; see detail for error message
