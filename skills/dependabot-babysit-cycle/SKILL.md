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

## Step 1.9: Early exit check

On every re-invocation (iteration ≥ 1 after increment in Step 1), check whether the
stop condition is **already satisfied** before running the full discovery:

- Read `all_open_prs` by calling `list_dependabot_prs` for each host (same scope as Step 2b).
- If the result is empty AND there were no repos with failing main CI in the last iteration
  (i.e., the previous Step 6 evaluated to "stop condition met"), print the silent exit message
  and stop:

```
Babysit — nothing to do. All eligible PRs merged and all mains passing.
Stop the /loop manually when ready.
```

If open PRs are found (GitHub has opened new PRs since the last cycle), continue to Step 2
normally — do not exit early.

**Note:** This check is a lightweight guard — it calls `list_dependabot_prs` but not
`get_pr_details` or any CI status call. Its purpose is to avoid a full verification round
when the work is already done.

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

Apply the classification priority table from `/dependabot-verify` (8 states):

| Priority | Status | Condition |
|----------|--------|-----------|
| 0 | ⚠️ ACTION REQUIRED | KB proactive match |
| 1 | ⚠️ ACTION REQUIRED | `ci_status == "failing"` OR comment contains `"requires manual action ⚠️"` |
| 2 | 🔄 NEEDS BRANCH UPDATE | `merge_state == "behind"` |
| 3 | 🔐 WAITING FOR ENV APPROVAL | `ci_status == "waiting_for_env_approval"` |
| 4 | ⏳ WAITING FOR CI | `ci_status == "pending"` |
| 5 | 👀 NEEDS REVIEW | No `APPROVED` review from current user AND no comment contains `"Dependabot PR reviewed ✅"` or `"requires manual action ⚠️"` |
| 6 | ✅ READY | Approved + automerge + CI passing + branch up to date |
| 7 | 👀 NEEDS REVIEW | catch-all |

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
  - If fix succeeds → call `get_branch_ci_status(host, token, repo, branch)` to confirm main is now passing.
    Update `main_health[repo].ci_status` to `"passing"` in memory so the stop condition in Step 6
    and the `unhealthy_repos` gate use fresh state.
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

---

## Step 4: Review / Update

For each open PR where:
- PR key (`"org/repo#123"`) NOT in `blocked_prs`
- PR repo NOT in `unhealthy_repos`

Route by current status:

| Status | Action |
|--------|--------|
| `👀 NEEDS REVIEW` | Execute full `/dependabot-review` Path B analysis for this PR. Use `prepare_merge` to approve and set automerge. |
| `🔄 NEEDS BRANCH UPDATE` | Call `update_branch(host, token, repo, pr_number)`. If `needs_manual_rebase` → attempt conflict resolution as per `/dependabot-update` Step 3.5. |
| `🔐 WAITING FOR ENV APPROVAL` | Call `prepare_merge(host, token, repo, pr_number, comment)` to approve pending environment deployments. |
| `⏳ WAITING FOR CI` | No action — wait for GitHub. |
| `✅ READY` | No action — GitHub automerge will handle it. |
| `⚠️ ACTION REQUIRED` | Skip here — handled in Step 5. |

After routing, record each PR whose repo is in `unhealthy_repos` with status `🔒 skipped`
and action `repo main failing` in the iteration report. These PRs are not processed in
Step 5 either — they are deferred to the next iteration.

---

## Step 5: Fix PRs with ACTION REQUIRED

For each open PR where:
- Status is `⚠️ ACTION REQUIRED`
- PR key NOT in `blocked_prs`
- PR repo NOT in `unhealthy_repos`

### Step 5a: Present diagnosis and ask for confirmation

Collect diagnosis from `get_pr_details`:
- `failing_checks[].name` — names of failing CI checks
- `diff_classification` — library, old_version, new_version, semver

Present:

```
PR <repo>#<number> — <title>
Problem: <merge conflict | CI failing: <check names> | both>
Library: <library> <old_version> → <new_version> (<semver>)

Attempt fix? (yes / no)
```

### Step 5b: Execute or block

- `tak`, `yes`, or empty reply → invoke the `/dependabot-fix` logic with `auto_confirm=true` for this PR
  (equivalent to `/dependabot-fix --yes <repo>:<pr_number>`).
  - Fix succeeds → record action `🔧 fixed <commit_url>`.
  - Fix fails or posts diagnostic comment → add `"org/repo#<number>"` to `blocked_prs`,
    record action `⏭️ blocked (fix failed)`.
- `nie` or `no` → add `"org/repo#<number>"` to `blocked_prs`,
  record action `⏭️ blocked (user declined)`.
- Any other input → re-present the prompt from Step 5a and wait for a valid response.

---

## Step 6: Save state

Write updated state back to `~/.claude/dependabot-babysit-state.json` using the Write tool:

```json
{
  "blocked_prs": ["<updated list>"],
  "blocked_repos": ["<updated list>"],
  "iteration": <current iteration number>,
  "start_time": "<preserved from initial write>",
  "scope": "<preserved from initial write>"
}
```

Always save **before** printing reports so that if the skill is interrupted mid-report,
state is not lost.

---

## Step 7: Evaluate stop condition

Collect current state after Steps 3–5:

```
open_eligible_prs = [pr for pr in all_open_prs if "org/repo#<number>" not in blocked_prs]
unhealthy_eligible_repos = [
    repo for repo, health in main_health.items()
    if health.ci_status == "failing" AND repo not in blocked_repos
]
```

**Stop condition met** when BOTH are true:
- `open_eligible_prs` is empty (all non-blocked PRs have been merged by GitHub)
- `unhealthy_eligible_repos` is empty (all non-blocked repos have passing main)

**If stop condition met:**

Print the final report (see Output Format → Final report below), then exit.
The `/loop` scheduler will invoke this skill again — on that next invocation,
the same check will detect "nothing to do" and exit silently. The user stops
the loop manually.

**If stop condition NOT met:**

Print the iteration report (see Output Format → Iteration report below) and exit normally.
The `/loop` scheduler will invoke the next cycle after the configured interval.

---

## Output Format

### Iteration report

```
## Babysit — iteration #<N>  [YYYY-MM-DD HH:MM]

### PRs
| Repo | PR | Status | Action |
|------|----|--------|--------|
| org/repo | [#123](url) | ✅ merged | — |
| org/repo | [#456](url) | ✅ READY | ⏳ waiting for GitHub automerge |
| org/repo | [#789](url) | ⚠️ ACTION REQUIRED | 🔧 fixed <commit_url> |
| org/repo | [#101](url) | ⚠️ ACTION REQUIRED | ⏭️ blocked (user declined) |
| org/repo | [#102](url) | ⏳ WAITING FOR CI | ⏳ waiting |
| org/repo | [#104](url) | 🔐 WAITING FOR ENV APPROVAL | 🔐 envs approved (1) |
| org/repo | [#103](url) | 🔒 skipped | repo main failing |

### Main branch health
| Repo | Branch | Status | Action |
|------|--------|--------|--------|
| org/repo | main | ✅ passing | — |
| org/repo2 | main | ❌ failing | 🔧 fixed (patch PR #42 opened) |
| org/repo3 | main | ❌ failing | ⏭️ blocked (user declined) |

Next iteration in <interval>.
```

**Action values for PRs:**
- `—` — no action taken (already merged, READY, or WAITING)
- `⏳ waiting for GitHub automerge` — READY, automerge set, waiting for GitHub
- `🔐 envs approved (<N>)` — N environment deployments approved; CI now running
- `🔧 fixed <commit_url>` — fix committed successfully
- `⏭️ blocked (user declined)` — user said no to fix prompt
- `⏭️ blocked (fix failed)` — fix attempted but could not be completed
- `🔒 skipped` — PR's repo has a failing main branch; deferred to next iteration

**Action values for main branches:**
- `—` — passing, no action needed
- `🔧 fixed (patch PR #N opened)` — fix PR created against main
- `🔧 fixed (commit <url>)` — fix committed directly to PR branch
- `⏭️ blocked (user declined)` — user said no
- `⏭️ blocked (fix failed)` — fix attempted but failed
- `ℹ️ not dependency-related` — CI failing but not caused by a Dependabot merge; out of scope

### Final report

```
## Babysit — done  [YYYY-MM-DD HH:MM]

All eligible PRs merged and all main branches passing.

### Blocked PRs (require manual attention)
| Repo | PR | Title | Blocked reason | Iteration |
|------|----|-------|----------------|-----------|
| org/repo | [#789](url) | Bump foo 1.0→2.0 | user declined fix | #2 |
| org/repo | [#999](url) | Bump bar 3.0→4.0 | fix failed | #3 |

### Blocked repos (main branch still failing)
| Repo | Reason | Iteration blocked |
|------|--------|-------------------|
| org/repo3 | user declined fix | #3 |

Total iterations: 5  |  Elapsed: ~50 minutes
```

Omit "Blocked PRs" section if `blocked_prs` is empty.
Omit "Blocked repos" section if `blocked_repos` is empty.
If both are empty, print instead: `No manual action required. Everything merged and green.`

### Silent exit (stop condition already met on re-entry)

When the stop condition is detected at the top of a fresh invocation (all eligible PRs
merged, all mains passing) and the iteration report was already printed in the previous
run, exit silently:

```
Babysit — nothing to do. All eligible PRs merged and all mains passing.
Stop the /loop manually when ready.
```
