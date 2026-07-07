---
name: dependabot-update
description: >
  Update branches and resolve dependency-file merge conflicts for all open Dependabot PRs.
  Works autonomously — updates branches that are behind, commits conflict resolutions for
  dependency files (go.mod, package-lock.json, etc.), and reports results in a summary table.
  Does not approve PRs, set automerge, or post analysis comments.
  Accepts an optional scope argument to limit work to a specific host, org, repo, or PR.
  Invoke with: /dependabot-update [host/org/repo:PR]
---

# /dependabot-update

You are executing the Dependabot branch-update workflow. Work autonomously — do not ask the
user for input. Process all PRs and present results at the end.

All GitHub I/O is performed through the `dependabot-reviewer` MCP server tools. Do not call
`gh` CLI for any GitHub operations — only for token acquisition. If the MCP server is not
present, stop and report an error.

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

---

## Step 2: Discover PRs

For each discovered host, apply the following routing based on the filter variables set in
Step 0:

```
if filter_pr is not null:
    # Skip list_dependabot_prs entirely — process single PR directly in Step 3
    prs = [synthetic entry: {number: filter_pr, repo: filter_repo, title: "(single PR)", url: ""}]
elif filter_repo is not null:
    prs = list_dependabot_prs(host, token, repo=filter_repo)
elif filter_org is not null:
    prs = list_dependabot_prs(host, token, org=filter_org)
else:
    prs = list_dependabot_prs(host, token)
```

Collect results into one list per host. Each item: `{number, repo, title, url}`.

If the combined list across all hosts is empty, print:
`No open Dependabot PRs matching the given filter.`
and stop.

---

## Step 3: Process each PR

Process PRs sequentially. For each PR:

1. Call `get_pr_details(host, token, repo=pr.repo, pr_number=pr.number)`.
   If this call fails → record status `❌ ERROR` with the error message and continue to next PR.

2. Route on `merge_state`:

| `merge_state` | Action |
|---------------|--------|
| `"behind"` | Call `update_branch(host, token, repo, pr_number)`. See Step 3a. |
| `"dirty"` | Proceed directly to Step 3.5 (conflict resolution). |
| `"clean"` or `"unknown"` | Record status `— NO ACTION` with detail `"branch is clean"` and continue to next PR. |

### Step 3a: Handle `"behind"` state

Call `update_branch(host, token, repo, pr_number)`. The tool returns
`{status: "done" | "needs_manual_rebase", branch_updated: bool, message: str}`.

- `status == "needs_manual_rebase"` → proceed to Step 3.5 (conflict resolution).
- `status == "done"` → re-fetch PR details:
  `get_pr_details(host, token, repo=pr.repo, pr_number=pr.number)`
  - If new `merge_state == "dirty"` → proceed to Step 3.5 (conflict resolution).
  - Otherwise → record status `✅ UPDATED` with detail `"branch updated"` and continue to next PR.

If `update_branch` throws an exception → record status `❌ ERROR` with the error message and
continue to next PR.

---

## Step 3.5: Conflict resolution

Triggered when: `update_branch` returned `"needs_manual_rebase"`, OR `merge_state` was
`"dirty"` from the start, OR `merge_state` became `"dirty"` after a successful `update_branch`.

**Dependency file extensions and names** (case-insensitive):

```
go.mod, go.sum,
package.json, package-lock.json, yarn.lock, pnpm-lock.yaml,
Gemfile, Gemfile.lock,
pyproject.toml, requirements.txt, requirements-dev.txt, requirements-test.txt,
Cargo.toml, Cargo.lock,
pom.xml, build.gradle, build.gradle.kts, gradle.lockfile,
composer.json, composer.lock,
Pipfile, Pipfile.lock,
poetry.lock
```

A file is a dependency file if its **basename** (the last path component) matches one of the
names above. All other files are "other files".

### Steps

1. Call `get_raw_diff(host, token, repo=pr.repo, pr_number=pr.number)`.
   If this call fails → record status `❌ ERROR` with the error message and continue to next PR.

2. Parse the unified diff to find all filenames that contain `<<<<<<<` conflict markers.
   These are the **conflicted files**.

3. Separate conflicted files into two groups:
   - **Dependency files** — basename matches the list above
   - **Other files** — everything else

4. If **other files** is non-empty → record status `⚠️ NEEDS MANUAL REVIEW` with detail
   `"non-dependency conflict in: <comma-separated filenames>"` and continue to next PR.
   Do not commit anything.

5. If **dependency files** is empty (no dependency files had conflicts, only others handled
   in step 4, or the diff had no conflict markers at all) → record status `⚠️ NEEDS MANUAL REVIEW`
   with detail `"no resolvable dependency conflicts found"` and continue to next PR.

6. For each dependency file with conflicts:
   a. Call `get_file_contents(host, token, repo=pr.repo, path=<file_path>, ref=<pr_branch>)`.
      The `pr_branch` is obtained from `get_pr_details` result (`head_ref` field).
      If this call fails → record status `❌ ERROR` with the error message and continue to next PR.
   b. In the file content, locate all conflict blocks delimited by:
      - `<<<<<<< <anything>` (start of conflict)
      - `=======` (separator between ours and theirs)
      - `>>>>>>> <anything>` (end of conflict)
   c. For each conflict block: **keep only the "ours" section** (the lines between
      `<<<<<<< ` and `=======`). This is the PR branch version — Dependabot's version
      always wins in dependency files.
   d. Remove the `<<<<<<< `, `=======`, and `>>>>>>> ` marker lines.
   e. Collect `{path: <file_path>, content: <resolved content>}`.

7. Re-fetch HEAD SHA: `get_pr_head_sha(host, token, repo=pr.repo, pr_number=pr.number)`.
   If this call fails → record status `❌ ERROR` with the error message and continue to next PR.

8. Call:
   ```
   commit_files(
     host=host,
     token=token,
     repo=pr.repo,
     branch=<pr_branch>,
     files=[{path, content}, ...],
     message="fix: resolve merge conflicts [dependabot skip]",
     head_sha=<sha from step 7>
   )
   ```
   - Success → record status `✅ CONFLICTS RESOLVED` with detail
     `"<N> dependency file(s) committed"`.
   - Error (e.g. stale SHA) → record status `❌ ERROR` with the error message.

---

## Step 4: Summary table

After all PRs are processed, display one table per host:

#### <host>

| Repo | PR | Status | Detail |
|------|----|--------|--------|
| `org/repo` | [#123](url) | ✅ UPDATED | branch updated |
| `org/repo` | [#456](url) | ✅ CONFLICTS RESOLVED | 2 dependency file(s) committed |
| `org/repo` | [#789](url) | ⚠️ NEEDS MANUAL REVIEW | non-dependency conflict in: main.go |
| `org/repo` | [#102](url) | — NO ACTION | branch is clean |
| `org/repo` | [#103](url) | ❌ ERROR | <error message> |

If no PRs were found for a host, say so explicitly:
`No open Dependabot PRs matching the given filter on <host>.`

**Status legend:**
- `✅ UPDATED` — branch was behind, successfully updated via `update_branch`
- `✅ CONFLICTS RESOLVED` — merge conflicts in dependency files resolved and committed
- `⚠️ NEEDS MANUAL REVIEW` — conflicts in non-dependency files, or no resolvable conflicts found
- `— NO ACTION` — branch is already up to date and clean
- `❌ ERROR` — unexpected error during processing; see detail
