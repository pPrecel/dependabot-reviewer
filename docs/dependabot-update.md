# /dependabot-update — Decision Flow

## Invocation

```
/dependabot-update [<scope>]
```

`<scope>` is optional. Supported formats:

| Format                                             | Effect                                          |
|----------------------------------------------------|-------------------------------------------------|
| *(none)*                                           | Process all PRs across all authenticated hosts  |
| `github.com/org/repo/pull/123`                     | Single PR (full URL)                            |
| `https://github.tools.sap/org/repo/pull/123`       | Single PR (full HTTPS URL)                      |
| `github.com/org/repo`                              | All PRs in one repo on a specific host          |
| `github.com/org`                                   | All PRs in one org on a specific host           |
| `github.com`                                       | All PRs on a specific host                      |
| `org/repo:123` or `org/repo#123`                  | Single PR (default host)                        |
| `org/repo`                                         | All PRs in one repo (all hosts)                 |
| `org`                                              | All PRs in one org (all hosts)                  |

Updates branches and resolves dependency-file merge conflicts for all open Dependabot/Renovate
PRs. Takes write actions: updates branches, commits conflict resolutions. Does **not** approve
PRs, set automerge, or post comments.

## Decision Tree

```
for each PR
│
├── get_pr_details()
│
├── merge_state == "behind"?
│   └── YES → update_branch()
│               ├── "needs_manual_rebase" → [Step 3.5 conflict resolution]
│               └── "done" → re-fetch get_pr_details()
│                               ├── merge_state == "dirty" → [Step 3.5 conflict resolution]
│                               └── otherwise → ✅ UPDATED
│
├── merge_state == "dirty"?
│   └── YES → [Step 3.5 conflict resolution]
│
└── merge_state == "clean" / "unknown"
    └── — NO ACTION
```

## Conflict Resolution (Step 3.5)

Triggered for `"behind"` (when update returns `needs_manual_rebase` or branch is still dirty
after update) and for `"dirty"`:

```
get_raw_diff()
│
├── identify all files with <<<<<<< markers
├── separate into: dependency files vs other files
│
├── other files non-empty?
│   └── YES → ⚠️ NEEDS MANUAL REVIEW  (no commit made)
│
└── dependency files non-empty?
    ├── gh api ... to get pr_branch name + get_pr_head_sha() for SHA
    ├── for each: get_file_contents(ref=pr_head_sha)
    │             resolve: keep "ours" (PR branch) version in each conflict block
    └── commit_files(branch=pr_branch, message="fix: resolve merge conflicts [dependabot skip]")
        ├── success → ✅ CONFLICTS RESOLVED
        └── error   → ❌ ERROR
```

**Dependency files resolved automatically:** go.mod, go.sum, package.json, package-lock.json,
yarn.lock, pnpm-lock.yaml, Gemfile, Gemfile.lock, pyproject.toml, requirements.txt,
Cargo.toml, Cargo.lock, pom.xml, build.gradle, build.gradle.kts, gradle.lockfile,
composer.json, composer.lock, Pipfile, Pipfile.lock, poetry.lock

**Conflict resolution rule:** in dependency files, the PR branch version (Dependabot's version)
always wins. This is the same rule used by `/dependabot-fix` when resolving conflicts.

## Status Legend

| Symbol | Status | Meaning |
|--------|--------|---------|
| ✅ | `UPDATED` | Branch was behind, successfully updated |
| ✅ | `CONFLICTS RESOLVED` | Dependency-file conflicts resolved and committed |
| ⚠️ | `NEEDS MANUAL REVIEW` | Conflicts in non-dependency files; cannot resolve automatically |
| — | `NO ACTION` | Branch is already up to date and clean |
| ❌ | `ERROR` | Unexpected error during processing; see detail |

## Summary Table Format

```
#### <host>

| Repo | PR | Status | Detail |
|------|----|--------|--------|
| `org/repo` | [#123](url) | ✅ UPDATED | branch updated |
| `org/repo` | [#456](url) | ✅ CONFLICTS RESOLVED | 2 dependency file(s) committed |
| `org/repo` | [#789](url) | ⚠️ NEEDS MANUAL REVIEW | non-dependency conflict in: main.go |
| `org/repo` | [#102](url) | — NO ACTION | branch is clean |
| `org/repo` | [#103](url) | ❌ ERROR | <error message> |
```
