---
name: dependabot-verify
description: >
  Read-only scan of all open Dependabot PRs where the current user is a requested reviewer.
  Reports the status of each PR without taking any write actions (no approvals, no comments,
  no automerge, no branch updates).
  Accepts an optional scope argument to limit work to a specific host, org, repo, or PR.
  Invoke with: /dependabot-verify [host/org/repo:PR]
---

# /dependabot-verify

You are executing the Dependabot PR verification workflow. Work autonomously — do not ask the user for input. Process all PRs and present results at the end. **Take no write actions.**

All GitHub I/O is performed through the `dependabot-reviewer` MCP server tools. If the MCP server is not present in the session or returns an error, stop and report the error — do not fall back to `gh` CLI or `curl`.

---

## Workflow

## Step 0: Parse arguments

Parse `ARGUMENTS` (the text after the skill name) before doing anything else. Produce three variables used throughout the rest of the workflow:

| Variable | Type | Description |
|----------|------|-------------|
| `filter_hosts` | `[string] \| null` | hosts to process; `null` = all authenticated hosts |
| `filter_repo` | `"org/repo" \| null` | exact repo to scope to |
| `filter_pr` | `int \| null` | single PR number; requires `filter_repo` |

Also derive:

- `filter_org` — the part before `/` in `filter_repo`, or the standalone `<org>` argument, or `null`

### Parsing rules (first match wins)

Strip a leading `https://` prefix first (do not pass the protocol to any tool).

| Input format | `filter_hosts` | `filter_repo` | `filter_pr` |
|-------------|----------------|---------------|-------------|
| `<host>/<org>/<repo>/pull/<PR>` (after stripping `https://`) | `[host]` | `org/repo` | PR |
| `<host>/<org>/<repo>` | `[host]` | `org/repo` | null |
| `<host>/<org>` | `[host]` | null | null |
| `<host>` (contains `.`) | `[host]` | null | null |
| `<org>/<repo>:<PR>` | null | `org/repo` | PR |
| `<org>/<repo>#<PR>` | null | `org/repo` | PR |
| `<org>/<repo>` | null | `org/repo` | null |
| `<org>` (no `.`) | null | null | null |
| *(empty)* | null | null | null |

**Host detection:** a path segment is a host if it contains `.`; otherwise it is an org.

### Errors

- `filter_hosts` contains a host not found in `gh auth status` output → stop:
  `"Error: not logged in to <host>. Run 'gh auth login --hostname <host>'."`
- `filter_pr` set but `filter_repo` is null → stop:
  `"Error: PR number requires a repo (use <org>/<repo>:<PR>)."`

---

### Step 1: Discover hosts and acquire tokens

```bash
gh auth status --show-token
```

Parse the output to extract every host and its token. Build a list of `{host, token}` pairs — one per authenticated host.

If `filter_hosts` is non-null (set in Step 0), keep only pairs where the host appears in `filter_hosts`. Validate: if any host in `filter_hosts` is not present in `gh auth status` output, stop with the error described in Step 0. Do not hardcode any host names.

---

### Step 1.5: Load knowledge base

Read the knowledge base as described in the agent's **Knowledge Base** section. Keep loaded entries available for all subsequent PR classification steps.

---

### Step 2: Discover PRs

For each discovered host, apply the following routing based on the filter variables set in Step 0:

```
if filter_pr is not null:
    # Skip list_dependabot_prs entirely — call get_pr_details directly in Step 3
    prs = [synthetic entry: {number: filter_pr, repo: filter_repo, title: "(single PR)", url: ""}]
elif filter_repo is not null:
    prs = list_dependabot_prs(host, token, repo=filter_repo)
elif filter_org is not null:
    prs = list_dependabot_prs(host, token, org=filter_org)
else:
    prs = list_dependabot_prs(host, token)
```

Deduplicate by PR number. If a host returns an error from `list_dependabot_prs`, record the error and continue with the other hosts.

If the combined list across all hosts is empty, print:
`No open Dependabot PRs matching the given filter.`
and stop.

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
