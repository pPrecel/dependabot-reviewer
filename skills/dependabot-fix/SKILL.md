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

## Step 1: Discover hosts and acquire tokens

```bash
gh auth status --show-token
```

Parse the output to extract every host and its token. Build a list of `{host, token}` pairs — one per authenticated host. Process all of them.

---

## Step 2: Discover PRs

For each host:

```
list_dependabot_prs(host=<host>, token=<token>)
```

---

## Step 3: Filter ACTION REQUIRED PRs

For each PR call:

```
get_pr_details(host, token, repo=pr.repo, pr_number=pr.number)
```

Keep only PRs where at least one comment body contains `"requires manual action ⚠️"`.

If no ACTION REQUIRED PRs found for a host → skip and note in summary.

---

## Step 4: Fix pipeline (per PR)

Process PRs sequentially. For each ACTION REQUIRED PR:

### Step 4a: Detect problem type + consult knowledge base

From `get_pr_details` result, determine which problems are present:
- `merge_state == "dirty"` → merge conflict
- `ci_status == "failing"` → failing CI
- Both → handle conflict first, then CI
- Neither → PR may already be fixed (stale comment); skip and note in report

**Knowledge base lookup:**

Read `~/.claude/dependabot-fix-knowledge/index.md` (if it exists — if not, proceed without).

For each entry in the index that matches the current problem type (`merge-conflict` or `ci-failure`), language, or package manager — read the full entry file. Use any matching entry as the primary fix strategy.

---

### Step 4b: Fix merge conflict (if `merge_state == "dirty"`)

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

3. Resolve conflicts: in dependency files (go.mod, go.sum, package-lock.json, Gemfile.lock, etc.) the Dependabot version always wins. For other files: prefer the PR branch (Dependabot) version for dependency-related lines; if a conflict cannot be resolved without understanding business logic, treat this file as unresolvable and go to Step 4d with a clear diagnosis. Produce clean resolved content with no conflict markers.

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

6. On success → record `conflict_fixed = true`, continue to Step 4c if CI also failing.
7. On failure (cannot determine correct resolution) → go to Step 4d, skip Step 4c.

---

### Step 4c: Fix failing CI (if `ci_status == "failing"`)

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

8. On success → record `ci_fixed = true`, proceed to Step 4e.
9. On failure (cannot identify cause or apply fix) → go to Step 4d.

---

### Step 4d: Diagnostic comment (fallback)

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

### Step 4e: Success comment + knowledge base update

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

## Step 5: Summary table

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
