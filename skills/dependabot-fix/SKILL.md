---
name: dependabot-fix
description: >
  Fix Dependabot or Renovate PRs with active problems (merge conflicts or failing CI).
  Without an argument, processes all open PRs where you are a requested reviewer.
  With a scope argument, limits work to the specified host, org, repo, or single PR.
  Runs analysis autonomously, then proposes a repair plan and waits for user confirmation before making any changes.
  Accepts an optional scope argument to limit work to a specific host, org, repo, or PR.
  Invoke with: /dependabot-fix [host/org/repo:PR]
---

# /dependabot-fix

Fix Dependabot or Renovate PRs that have active problems — merge conflicts or failing CI.
Without an argument, processes all open PRs where you are a requested reviewer. With a scope
argument, limits work to the specified host, org, repo, or single PR.

All GitHub I/O is performed through the `dependabot-reviewer` MCP server tools. Do not
call `gh` CLI for any GitHub operations — only for token acquisition. If the MCP server
is not present, stop and report an error.

---

## Step 0: Parse arguments

Parse `ARGUMENTS` (the text after the skill name) before doing anything else. Produce three
variables used throughout the rest of the workflow:

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

## Step 1: Discover hosts and acquire tokens

```bash
gh auth status --show-token
```

Parse the output to extract every host and its token. Build a list of `{host, token}` pairs
— one per authenticated host.

If `filter_hosts` is non-null (set in Step 0), keep only pairs where the host appears in
`filter_hosts`. Validate: if any host in `filter_hosts` is not present in `gh auth status`
output, stop with the error described in Step 0. Do not hardcode any host names.

Store `{host, token}` pairs for use in all subsequent steps.

---

## Step 2: Load knowledge base

Read `~/.claude/dependabot-fix-knowledge/index.md`.

If the file does not exist, proceed without — no error.

For each entry listed in the index, read the full entry file. Keep all entries in memory
for use during analysis and fix planning in Steps 3 and 4.

---

## Step 3: Analyse (autonomous — no user interaction)

Run the analysis that matches `target_type`.

### 3a: PR analysis (`target_type == "pr"`)

1. Call `get_pr_details(host, token, repo, pr_number)`.
2. Determine problem types present:
   - `merge_state == "dirty"` → **merge conflict**
   - `ci_status == "failing"` → **failing CI**
   - Both → both problems; conflict will be addressed first
   - Neither → note "no active problem detected (stale ACTION REQUIRED comment?)" and skip to Step 4 directly
3. If **failing CI**: for each entry in `failing_checks`, call
   `get_check_logs(host, token, repo, check_run_id=<id>)` and read the returned log file.
4. If **merge conflict**: call `get_raw_diff(host, token, repo, pr_number)` and identify
   files containing `<<<<<<<` conflict markers.
5. Match findings against knowledge base entries loaded in Step 2.

### 3b: Repo/branch analysis (`target_type == "repo"`)

1. Call `get_branch_ci_status(host, token, repo, branch="main")`.
   - If 404 → retry with `branch="master"`.
   - If both fail → stop with error.
2. If `ci_status != "failing"` → report "Main branch CI is not failing" and stop.
3. For each entry in `failing_checks`, call `get_check_logs` and read the log file.
4. Call `list_recently_merged_dependabot_prs(host, token, since=<ISO date 14 days ago>)`.
   Filter to PRs in this `repo`. Identify which merged PR most likely introduced the failure
   by correlating merge timestamps with the first failing CI run.
5. Match findings against knowledge base entries.

### 3c: Scope check

If the root cause does not appear to be a Dependabot or Renovate dependency update
(e.g. the failure predates any recent dependency merges, or the logs point to unrelated
infrastructure), state this clearly and stop:

`"This failure does not appear to be caused by a Dependabot/Renovate update. Scope of this skill is dependency-update problems only."`

---

## Step 4: Propose repair plan and wait for confirmation

Present the analysis result and a concrete repair plan. **Do not make any changes yet.**

### Format

```
## Analysis: <repo>#<pr_number>  (or <repo> @ <branch>)

**Problem:** <merge conflict | CI failing: <check names> | both>
**Root cause:** <concrete description from logs / diff>
**Knowledge base:** <"matches entry NNN: <title>" | "no matching entry">

**Repair plan:**
1. <step 1 — concrete action, e.g. "Replace NewSimpleClientset → NewClientset in 3 files">
2. <step 2 — e.g. "Commit to PR branch with message 'fix: SA1019 [dependabot skip]'">
...

**Approach:** <one of: commit fix to PR branch | commit resolved conflicts to PR branch |
               create patch branch + open PR | post diagnostic comment (infra issue)>
**Files to change:** <comma-separated list, or "none (diagnostic comment only)">

Proceed? (yes / no / feedback)
```

### Response handling

- `tak`, `yes`, or empty reply → proceed to Step 5
- `nie` or `no` → stop without any changes; print "Cancelled — no changes were made."
- Any other text → treat as refinement feedback: update the plan accordingly and present
  the revised plan again with the same question. Repeat until `tak`/`nie`.

### Methodology selection

Choose the approach based on problem type:

| Problem | Approach |
|---------|----------|
| CI failing on PR branch | Commit fix directly to PR branch |
| Merge conflict on PR branch | Commit resolved conflicts to PR branch |
| CI failing on main after merge | Create patch branch (based on `main`/`master`) + open PR to that same base branch |
| Complex API migration on PR branch | Commit migration fix to PR branch |
| Infrastructure problem (e.g. GCP IAM, CI runner misconfiguration) | Post diagnostic comment — cannot be fixed with code |

---

## Step 5: Execute

Execute the approved plan. Log each completed action internally (used in the success
comment and in unexpected-situation messages).

### 5a: Fix merge conflict (if applicable)

1. For each conflicted file, fetch content from the PR branch:
   `get_file_contents(host, token, repo, path=<path>, ref=<pr_branch>)`
   Also fetch from base branch if needed for reference:
   `get_file_contents(host, token, repo, path=<path>, ref=<base_branch>)`
2. Resolve: in dependency files (go.mod, go.sum, package-lock.json, Gemfile.lock, etc.)
   the Dependabot/Renovate version always wins. For other files: prefer the PR branch
   version for dependency-related lines.
3. Fetch current HEAD SHA: `get_pr_head_sha(host, token, repo, pr_number)`
4. Commit resolved files:
   ```
   commit_files(host, token, repo,
     branch=<pr_branch>,
     files=[{path, content}, ...],
     message="fix: resolve merge conflicts [dependabot skip]",
     head_sha=<sha>)
   ```
5. If conflict cannot be resolved without understanding business logic → go to Step 5d.

### 5b: Fix failing CI (if applicable)

1. Fetch the relevant source files identified during analysis:
   `get_file_contents(host, token, repo, path=<path>, ref=<pr_branch>)`
2. Apply the fix to the file content.
3. Re-fetch HEAD SHA (always re-fetch after any previous `commit_files` call):
   `get_pr_head_sha(host, token, repo, pr_number)`
4. Commit:
   ```
   commit_files(host, token, repo,
     branch=<pr_branch>,
     files=[{path, content}, ...],
     message="fix: resolve CI failure in <check_name> [dependabot skip]",
     head_sha=<sha>)
   ```

### 5c: Create patch branch + PR (main branch case)

1. Determine base branch name (`main` or `master` — whichever responded in Step 3b).
2. Fetch HEAD SHA of the base branch:
   ```
   get_branch_head_sha(host, token, repo, branch=<base_branch>)
   ```
3. Apply fixes to files, then commit to a new branch:
   ```
   commit_files(host, token, repo,
     branch="fix/dependabot-ci-<short-description>",
     files=[{path, content}, ...],
     message="fix: restore CI after dependency update [dependabot skip]",
     head_sha=<base_branch_sha>)
   ```
   `commit_files` creates the branch automatically when the branch name is new
   and `head_sha` points to an existing commit.
4. Open PR:
   ```
   create_pull_request(host, token, repo,
     title="fix: restore CI after dependency update",
     head="fix/dependabot-ci-<short-description>",
     base=<base_branch>,
     body="Automated fix for CI failure introduced by a Dependabot/Renovate merge.")
   ```

### 5d: Unexpected situation — pause and ask

Stop autonomous execution and return to the user when:
- A file to be modified does not exist on the PR branch
- A conflict cannot be resolved without business logic knowledge
- `commit_files` returns an error (e.g. stale HEAD SHA)
- The knowledge-base fix does not apply cleanly to the current file version

Present:

```
## Unexpected situation — decision required

**What I did:** <completed steps>
**Stuck on:** <concrete problem>
**Options:**
1. <option A — e.g. "Skip this file and commit the rest">
2. <option B — e.g. "Provide the correct resolution for <file> and I will commit it">
3. Leave a diagnostic comment on the PR and stop

What should I do?
```

Wait for user response and act accordingly. Option 3 triggers Step 6c (diagnostic comment).

---

## Step 6: Post-execution

### 6a: Success comment

Post a comment on the PR (or the newly created PR for the main-branch case):

```
post_pr_comment(host, token, repo, pr_number, body="""
Automatic fix applied ✅

**{library}**: {old_version} → {new_version}  (omit if not a single-library bump)
**Fixed:** {merge conflict | CI: <check-name> | merge conflict + CI: <check-name>}
**Commit:** {commit_url}
**Knowledge base:** {used entry: "<title>" | new entry recorded: "<title>" | no entry recorded}
""")
```

For the main-branch case, print the new PR URL to the user as well.

### 6b: Knowledge base update

Evaluate whether the fix is generic enough to be reused in another repo:

Record when:
- Fix is reproducible given the same problem type + language/package manager
- Fix does not depend on repo-specific business logic
- Fix could save time on a future PR

Do not record when:
- Fix was specific to this repo's internal structure
- Fix required understanding of business logic beyond dependency updates

If recording, determine the next sequential ID by listing files in
`~/.claude/dependabot-fix-knowledge/entries/`. Write the new entry:

```markdown
---
id: <NNN>
title: <descriptive title>
problem_type: ci-failure | merge-conflict
trigger_pattern: "<log string or condition that identifies this problem>"
languages: [<go|python|javascript|...>]
package_managers: [<go-modules|npm|pip|...>]
---

## Problem

<What the failure looks like — exact error message or condition>

## Fix

<Concrete steps: which files to check, what to change, how to call commit_files>

## Example

PR: {repo}#{pr_number} — bumped {library} {old_version} → {new_version}
```

If `~/.claude/dependabot-fix-knowledge/index.md` does not exist yet, create it:

```markdown
# dependabot-fix knowledge base

Accumulated fix patterns. Read this index before fixing any ACTION REQUIRED PR.

```

Append one line to the index:

```
- [<NNN> <title>](entries/<filename>) — <problem_type>: <trigger_pattern>
```

### 6c: Diagnostic comment (infrastructure / unfixable case)

When the problem cannot be fixed with code (infrastructure issue, or Step 5d option 3):

```
post_pr_comment(host, token, repo, pr_number, body="""
Unable to fix automatically ⚠️

**What was investigated:**
<description of what was checked: logs read, files examined, diff analysed>

**Diagnosis:**
<specific reason why automatic fix is not possible — be concrete>

**Recommended manual action:**
<numbered step-by-step instructions for a human>
""")
```
