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

### Step 1: Discover hosts and acquire tokens

```bash
gh auth status --show-token
```

Parse the output to extract every host and its token. Build a list of `{host, token}` pairs — one per authenticated host. Process all of them; do not hardcode any host names.

---

### Step 1.5: Load knowledge base

Read the knowledge base as described in the agent's **Knowledge Base** section. Keep loaded entries available for all subsequent PR classification steps.

---

### Step 2: Discover PRs

For each discovered host, call:

```
list_dependabot_prs(host=<host>, token=<token>)
```

Collect results into one list per host, deduplicated by PR number. If a host returns an error, record the error and continue with the other hosts.

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
| 0 | ⚠️ `ACTION REQUIRED` | KB proactive match: PR repo + diff matches a knowledge base entry with a `## Proactive detection` section (even if CI is passing or pending) |
| 1 | ⚠️ `ACTION REQUIRED` | `ci_status == "failing"`, OR any comment body contains `"requires manual action ⚠️"` |
| 2 | 🔄 `NEEDS BRANCH UPDATE` | `merge_state == "behind"` |
| 3 | ⏳ `WAITING FOR CI` | `ci_status == "pending"` |
| 4 | 👀 `NEEDS REVIEW` | No `APPROVED` review from current user AND no comment contains `"Dependabot PR reviewed ✅"` or `"requires manual action ⚠️"` |
| 5 | ✅ `READY` | `APPROVED` review from current user, `auto_merge_set == true`, `ci_status == "passing"`, `merge_state != "behind"` |
| 6 | 👀 `NEEDS REVIEW` | Catch-all |

**KB proactive match (Priority 0):**

Before applying the standard priority table, scan loaded knowledge base entries for any that have both a `repos` field and a `## Proactive detection` section. For each such entry, check if `pr.repo` is in the `repos` list and whether the PR's diff matches the described pattern. If matched, classify as `⚠️ ACTION REQUIRED` and set the Detail field to `known pattern: <entry title>`.

**Detail field per status:**
- `⚠️ ACTION REQUIRED` → list failing check names, e.g. `CI: test-unit FAILURE`; if a knowledge base entry matches (CI failure or proactive), append `(known pattern: <entry title>)`
- `🔄 NEEDS BRANCH UPDATE` → `branch is behind <base-branch-name>`
- `⏳ WAITING FOR CI` → count of pending checks, e.g. `3 checks pending`
- `👀 NEEDS REVIEW` → `no review yet`
- `✅ READY` → `—`
- `👀 NEEDS REVIEW` (catch-all) → `needs attention`

If fetching data for a PR fails, record status as `❌ ERROR` and detail as the error message. Continue to the next PR.

---

### Step 4: Present summary tables

After all PRs are processed, display one table per host:

#### <host>

| Repo | PR | Status | Detail |
|------|----|--------|--------|
| `org/repo` | [#123](url) | ✅ READY | — |
| `org/repo` | [#456](url) | ⚠️ ACTION REQUIRED | CI: test-unit FAILURE |
| `org/repo` | [#789](url) | ⏳ WAITING FOR CI | 3 checks pending |
| `org/repo` | [#102](url) | 🔄 NEEDS BRANCH UPDATE | branch is behind main |
| `org/repo` | [#103](url) | 👀 NEEDS REVIEW | no review yet |

If no PRs were found for a host, say so explicitly:
`No open Dependabot PRs awaiting review on <host>.`

**Status legend:**
- `✅ READY` — approved, automerge set, all CI green, branch up to date
- `⚠️ ACTION REQUIRED` — failing CI or prior analysis flagged manual action
- `🔄 NEEDS BRANCH UPDATE` — branch is behind base, needs update before merge
- `⏳ WAITING FOR CI` — checks still running, no action needed yet
- `👀 NEEDS REVIEW` — PR has not been reviewed or analysed yet
- `❌ ERROR` — failed to fetch PR data; see detail for error message

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

````
#### Main branch health — <host>

| Repo | Branch | Status | Failing checks |
|------|--------|--------|----------------|
| `org/repo` | main | ✅ passing | — |
| `org/repo` | main | ❌ failing | build, lint |
| `org/repo` | main | ⏳ pending | — |
| `org/repo` | main | ❓ unknown | — |
| `org/repo` | main | ❌ ERROR | <error message> |
````

Map `ci_status` from `get_branch_ci_status` to display status:
- `"passing"` → `✅ passing`
- `"failing"` → `❌ failing` (list `failing_checks[].name` comma-separated in "Failing checks" column)
- `"pending"` → `⏳ pending`
- `"unknown"` → `❓ unknown`
- error → `❌ ERROR`

If no repos were found for a host: `No repositories to check on <host>.`
