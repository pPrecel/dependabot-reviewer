---
name: dependabot-babysit-cycle
description: >
  One iteration of the dependabot-babysit loop. Reads session state, runs verify →
  main health check → review/update → fix → stop-condition evaluation. Not intended
  to be invoked directly — use /dependabot-babysit instead.
  Invoke with: /dependabot-babysit-cycle [scope]
---

# /dependabot-babysit-cycle

One iteration of the babysit loop. Runs autonomously except for fix confirmations.

All GitHub I/O is performed through the `dependabot-reviewer` MCP server tools. Do not
call `gh` CLI for any GitHub operations — only for token acquisition. If the MCP server
is not present, stop and report an error.

---

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

| Input format                                              | `filter_hosts` | `filter_repo` | `filter_pr` |
|-----------------------------------------------------------|----------------|---------------|-------------|
| `<host>/<org>/<repo>/pull/<PR>` (after stripping `https://`) | `[host]`    | `org/repo`    | PR          |
| `<host>/<org>/<repo>`                                     | `[host]`       | `org/repo`    | null        |
| `<host>/<org>`                                            | `[host]`       | null          | null        |
| `<host>` (contains `.`)                                   | `[host]`       | null          | null        |
| `<org>/<repo>:<PR>`                                       | null           | `org/repo`    | PR          |
| `<org>/<repo>#<PR>`                                       | null           | `org/repo`    | PR          |
| `<org>/<repo>`                                            | null           | `org/repo`    | null        |
| `<org>` (no `.`)                                          | null           | null          | null        |
| *(empty)*                                                 | null           | null          | null        |

**Host detection:** a path segment is a host if it contains `.`; otherwise it is an org.

### Errors

- `filter_hosts` contains a host not found in `gh auth status` output → stop:
  `"Error: not logged in to <host>. Run 'gh auth login --hostname <host>'."`
- `filter_pr` set but `filter_repo` is null → stop:
  `"Error: PR number requires a repo (use <org>/<repo>:<PR>)."`

---

## Step 1: Load state

Read `~/.claude/dependabot-babysit-state.json`.

If the file does not exist, initialise:
```json
{
  "blocked_prs": [],
  "blocked_repos": [],
  "iteration": 0,
  "start_time": "<now>",
  "scope": null
}
```

Increment `iteration` by 1 (first real iteration = 1).

Keep in memory:
- `blocked_prs` — list of strings like `"org/repo#123"`. These PRs are never processed.
- `blocked_repos` — list of strings like `"org/repo"`. Main branch of these repos is never checked.
- `iteration` — current cycle number (after increment).
- `start_time` — ISO timestamp of first invocation (used in final report).

---

## Step 1.5: Load knowledge base

Read the knowledge base as described in the agent's **Knowledge Base** section. Keep loaded entries available for PR classification in Step 2c and correlation in Step 3a.

---

## Step 2: Verify — snapshot all PRs and main branches

### Step 2a: Discover hosts and acquire tokens

```bash
gh auth status --show-token
```

Parse output to build `{host, token}` pairs. If `filter_hosts` is non-null (set in Step 0), keep only pairs where the host appears in `filter_hosts`.

### Step 2b: Discover open PRs

For each `{host, token}`:

```
if filter_repo is not null:
    prs = list_dependabot_prs(host, token, repo=filter_repo)
elif filter_org is not null:
    prs = list_dependabot_prs(host, token, org=filter_org)
else:
    prs = list_dependabot_prs(host, token)
```

### Step 2c: Classify each PR

For each PR not in `blocked_prs` (match format `"org/repo#123"`):

```
get_pr_details(host, token, repo=pr.repo, pr_number=pr.number)
```

Apply the classification priority table from `/dependabot-verify` (7 states):

| Priority | Status | Condition |
|----------|--------|-----------|
| 0 | ⚠️ ACTION REQUIRED | KB proactive match |
| 1 | ⚠️ ACTION REQUIRED | `ci_status == "failing"` OR comment contains `"requires manual action ⚠️"` |
| 2 | 🔄 NEEDS BRANCH UPDATE | `merge_state == "behind"` |
| 3 | ⏳ WAITING FOR CI | `ci_status == "pending"` |
| 4 | 👀 NEEDS REVIEW | No `APPROVED` review from current user AND no comment contains `"Dependabot PR reviewed ✅"` or `"requires manual action ⚠️"` |
| 5 | ✅ READY | Approved + automerge + CI passing + branch up to date |
| 6 | 👀 NEEDS REVIEW | catch-all |

PRs in `blocked_prs` are excluded entirely from this classification.

### Step 2d: Collect main branch CI status

For each unique `(host, repo)` across all open PRs, plus repos from
`list_recently_merged_dependabot_prs(host, token, since=<14 days ago>)`:

```
get_branch_ci_status(host, token, repo, branch="main")
```

If 404 → retry with `branch="master"`. If both fail → record as `❌ ERROR`.

Exclude repos in `blocked_repos` from collection.

Store results as `main_health`: map of `"org/repo"` → `{branch, ci_status, failing_checks}`.

---

## Step 3: Main branch health check (PRIORITY — before review/fix)

For each repo in `main_health` where `ci_status == "failing"` AND repo NOT in `blocked_repos`:

### Step 3a: Determine if failure is dependency-related

1. Call `list_recently_merged_dependabot_prs(host, token, since=<14 days ago>)` filtered to this repo.
2. For each failing check, call `get_check_logs(host, token, repo, check_run_id=<id>)` and read the log file.
3. Correlate: find which merged Dependabot PR most likely introduced the failure by comparing
   merge timestamps to the first CI failure timestamp. Use the same logic as `/dependabot-fix` Step 4b.
4. If no recently merged Dependabot/Renovate PRs in the past 14 days → **skip** (not in scope).
   Do NOT add to `blocked_repos`. Do NOT gate review for this repo.
5. If correlation is found → proceed to Step 3b.

### Step 3b: Ask for confirmation

Present:

```
Main branch CI failing in <repo>
Likely caused by: <library> <old_version> → <new_version> (merged <date>, PR <url>)
Failing checks: <check names>

Proceed with /dependabot-fix? (yes / no)
```

### Step 3c: Execute or block

- `tak`, `yes`, or empty reply → invoke the `/dependabot-fix` logic with `auto_confirm=true` for this repo
  (equivalent to `/dependabot-fix --yes <repo>`).
  - If fix succeeds → re-check `get_branch_ci_status` to confirm main is now passing.
  - If fix fails (diagnostic comment posted, or unexpected situation hit) → add `"org/repo"` to `blocked_repos`.
- `nie` or `no` → add `"org/repo"` to `blocked_repos`.
- Any other input → re-present the prompt from Step 3b and wait for a valid response.

### Step 3d: Build `unhealthy_repos` gate

After processing all failing repos, collect:

```
unhealthy_repos = { repo | main_health[repo].ci_status == "failing" AND repo NOT in blocked_repos }
```

PRs in `unhealthy_repos` are **excluded from Steps 4 and 5**. This prevents reviewing or
approving PRs into a broken pipeline.
