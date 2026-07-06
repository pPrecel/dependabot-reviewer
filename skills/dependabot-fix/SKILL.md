---
name: dependabot-fix
description: >
  Fix a single selected Dependabot or Renovate PR (or a repository whose main branch
  CI broke after merging such a PR). Runs analysis autonomously, then proposes a repair
  plan and waits for user confirmation before making any changes.
  Invoke with: /dependabot-fix [host] <ref>
  Examples: /dependabot-fix kyma-project/cli#2945
            /dependabot-fix github.tools.sap kyma/warden#209
            /dependabot-fix https://github.com/kyma-project/cli/pull/2945
            /dependabot-fix kyma-project/cli
---

# /dependabot-fix

Fix a single Dependabot or Renovate problem — either a PR in ACTION REQUIRED state or a
repository whose main-branch CI broke after merging such a PR.

All GitHub I/O is performed through the `dependabot-reviewer` MCP server tools. Do not
call `gh` CLI for any GitHub operations — only for token acquisition. If the MCP server
is not present, stop and report an error.

---

## Step 1: Parse argument and acquire token

### 1a: Read the argument

The skill is invoked as `/dependabot-fix [host] <ref>`. Parse `ARGUMENTS` (the text
after the skill name).

Supported formats — apply the **first matching rule**:

| Rule | Pattern | Result |
|------|---------|--------|
| 1 | Argument is a URL: `https://<host>/...` | Extract host from URL domain. If URL contains `/pull/<N>`, it is a PR ref; otherwise it is a repo ref. |
| 2 | Argument starts with a known host token (word containing a `.` and matching an authenticated host, e.g. `github.tools.sap`) followed by `org/repo#N` | explicit host + PR ref |
| 3 | Argument starts with a known host token followed by `org/repo` | explicit host + repo ref |
| 4 | Argument matches `org/repo#N` (no host prefix) | default host + PR ref |
| 5 | Argument matches `org/repo` (no host prefix, no `#`) | default host + repo ref |
| 6 | Argument is empty or not parseable | Ask once: `"Podaj PR lub repo do naprawy (np. org/repo#123 lub https://github.com/org/repo/pull/123):"`. If the reply still does not match any rule above, print an error and stop. |

### 1b: Resolve host and acquire token

Run:
```bash
gh auth status --show-token
```

Parse the output to extract every `{host, token}` pair.

Host resolution:
1. If a URL was provided → host is the URL domain (e.g. `github.com`, `github.tools.sap`)
2. If an explicit host was provided in the argument → use it
3. If no host was provided → use `github.com` as default
4. If the resolved host is not present in `gh auth status` output → stop with error:
   `"Error: not logged in to <host>. Run 'gh auth login --hostname <host>' or provide the host explicitly."`

Store `{host, token, target_type, repo, pr_number_or_branch}` for use in all subsequent steps.

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

## Step 4: Discover PRs

For each host:

```
list_dependabot_prs(host=<host>, token=<token>)
```

---

## Step 5: Filter ACTION REQUIRED PRs

For each PR call:

```
get_pr_details(host, token, repo=pr.repo, pr_number=pr.number)
```

Keep only PRs where at least one comment body contains `"requires manual action ⚠️"`.

If no ACTION REQUIRED PRs found for a host → skip and note in summary.

---

## Step 6: Fix pipeline (per PR)

Process PRs sequentially. For each ACTION REQUIRED PR:

### Step 6a: Detect problem type + consult knowledge base

From `get_pr_details` result, determine which problems are present:
- `merge_state == "dirty"` → merge conflict
- `ci_status == "failing"` → failing CI
- Both → handle conflict first, then CI
- Neither → PR may already be fixed (stale comment); skip and note in report

**Knowledge base lookup:**

Read `~/.claude/dependabot-fix-knowledge/index.md` (if it exists — if not, proceed without).

For each entry in the index that matches the current problem type (`merge-conflict` or `ci-failure`), language, or package manager — read the full entry file. Use any matching entry as the primary fix strategy.

---

### Step 6b: Fix merge conflict (if `merge_state == "dirty"`)

1. Call `get_raw_diff(host, token, repo, pr_number)` to get the raw diff text. Identify files containing `<<<<<<<` conflict markers.

2. For each conflicted file, fetch its content from the PR branch:
   ```
   get_file_contents(host, token, repo, path=<path>, ref=<pr_branch>)
   ```
   The base branch version is available for reference if needed:
   ```
   get_file_contents(host, token, repo, path=<path>, ref=<base_branch>)
   ```
   The PR branch file will contain `<<<<<<<` conflict markers.

3. Resolve conflicts: in dependency files (go.mod, go.sum, package-lock.json, Gemfile.lock, etc.) the Dependabot version always wins. For other files: prefer the PR branch (Dependabot) version for dependency-related lines; if a conflict cannot be resolved without understanding business logic, treat this file as unresolvable and go to Step 6d with a clear diagnosis. Produce clean resolved content with no conflict markers.

4. Get the current HEAD SHA of the PR branch:
   ```
   get_pr_head_sha(host, token, repo, pr_number)
   ```

5. Commit the resolved files:
   ```
   commit_files(
     host, token, repo,
     branch=<pr_branch>,
     files=[{path: <path>, content: <resolved_content>}, ...],
     message="fix: resolve merge conflicts [dependabot skip]",
     head_sha=<current_head_sha>,
   )
   ```

6. On success → record `conflict_fixed = true`, continue to Step 6c if CI also failing.
7. On failure (cannot determine correct resolution) → go to Step 6d, skip Step 6c.

---

### Step 6c: Fix failing CI (if `ci_status == "failing"`)

1. For each entry in `failing_checks`:
   First, get the check run IDs for the current HEAD SHA:
   ```
   get_check_run_ids(host, token, repo, head_sha=<pr_head_sha>)
   ```
   Match failing check names to their numeric `id`. Then call:
   ```
   get_check_logs(host, token, repo, check_run_id=<id>)
   ```

2. Read each log file using the `Read` tool (the full path returned by `get_check_logs`).

3. Identify root cause from logs. Common patterns:
   - `"go mod tidy"` or `"go: inconsistent vendoring"` → run `go mod tidy` equivalent: fetch `go.mod`/`go.sum`, regenerate
   - `"cannot find module"` → dependency not in go.sum
   - Snapshot/golden file mismatch → update snapshot file
   - Test hardcoded an old version string → update assertion
   - Lint: unused import, formatting → fix the specific line

4. Fetch the relevant source files:
   ```
   get_file_contents(host, token, repo, path=<path>, ref=<pr_branch>)
   ```

5. Apply the fix — modify file content to resolve the identified issue.

6. Get the current HEAD SHA of the PR branch (re-fetch after any previous commit_files call):
   ```
   get_pr_head_sha(host, token, repo, pr_number)
   ```

7. Commit:
   ```
   commit_files(
     host, token, repo,
     branch=<pr_branch>,
     files=[{path: <path>, content: <fixed_content>}, ...],
     message="fix: resolve CI failure in <check_name> [dependabot skip]",
     head_sha=<current_head_sha>,
   )
   ```

8. On success → record `ci_fixed = true`, proceed to Step 6e.
9. On failure (cannot identify cause or apply fix) → go to Step 6d.

---

### Step 6d: Diagnostic comment (fallback)

When automatic fix is not possible:

```
post_pr_comment(
  host, token, repo, pr_number,
  body="""Unable to fix automatically ⚠️

**What was investigated:**
<description of what was checked: diff, log files read, files examined>

**Diagnosis:**
<specific reason why automatic fix failed — be concrete>

**Recommended manual action:**
<numbered step-by-step instructions for a human>
"""
)
```

Set PR result to `⚠️ NEEDS MANUAL ACTION`.

---

### Step 6e: Success comment + knowledge base update

Post success comment:

```
post_pr_comment(
  host, token, repo, pr_number,
  body="""Automatic fix applied ✅

**{library}**: v{old_version} → v{new_version}
**Fixed:** {merge conflict | CI: check-name | merge conflict + CI: check-name}
**Commit:** {commit_url}
**Knowledge base:** {used entry: "title" | new entry recorded: "title" | no entry recorded}
"""
)
```

**Knowledge base update:**

Evaluate: is this fix generic enough to recur on another repo? Use these criteria:

Record when:
- Fix is reproducible given the same problem type + language/package manager
- Fix does not depend on repo-specific business logic
- Fix could save time on a future PR

Do not record when:
- Fix was specific to this repo's internal structure
- Fix required understanding business logic beyond dependency updates

If recording, write a new file to `~/.claude/dependabot-fix-knowledge/entries/` with a sequential numeric prefix (check existing files to determine next number):

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

If `index.md` does not exist yet, create it first with this header:

```markdown
# dependabot-fix knowledge base

Accumulated fix patterns. Read this index before fixing any ACTION REQUIRED PR.

```

Then append one line to `~/.claude/dependabot-fix-knowledge/index.md`:

```
- [{NNN} {title}](entries/{filename}) — {problem_type}: {trigger_pattern}
```

---

## Step 7: Summary table

Present one table per host after processing all PRs:

### <host>

| Repo | PR | Problem | Status |
|------|----|---------|--------|
| `org/repo` | [#123](url) | merge conflict | ✅ FIXED |
| `org/repo` | [#456](url) | CI: test-unit | ✅ FIXED |
| `org/repo` | [#789](url) | CI: lint | ⚠️ NEEDS MANUAL ACTION |
| `org/repo` | [#102](url) | merge conflict + CI | ✅ FIXED |
| `org/repo` | [#111](url) | — | ❌ ERROR |

Status legend:
- `✅ FIXED` — commit pushed, problem resolved
- `⚠️ NEEDS MANUAL ACTION` — could not fix automatically; diagnostic comment left on PR
- `❌ ERROR` — unexpected error fetching PR data; see detail

If no ACTION REQUIRED PRs found for a host: `No ACTION REQUIRED Dependabot PRs found on <host>.`
