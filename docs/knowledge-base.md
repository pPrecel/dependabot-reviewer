# Shared Knowledge Base

All skills share a persistent knowledge base of known CI failure patterns and fix strategies. It accumulates across sessions and is maintained by the `/dependabot-fix` skill.

## Location

```
~/.claude/dependabot-fix-knowledge/
├── index.md           ← index of all entries (one line per entry)
└── entries/
    ├── 001-*.md
    ├── 002-*.md
    └── ...
```

## Purpose

The knowledge base is a **shared cache** between `/dependabot-review`, `/dependabot-verify`, and `/dependabot-fix`. When a CI failure pattern is seen and fixed in one repo, the fix strategy is recorded so that:

- `/dependabot-review` can include the known root cause in its ACTION REQUIRED comments
- `/dependabot-verify` can show `(known pattern: <title>)` in its Detail column
- `/dependabot-fix` can apply the fix strategy directly without re-reading logs

## Loading

Each skill loads the knowledge base **once at session start**, before processing any PRs:

1. Read `~/.claude/dependabot-fix-knowledge/index.md` with the `Read` tool
2. For each entry referenced, read the full entry file
3. Keep all entries in memory for the duration of the session

If `index.md` does not exist, proceed without — do not treat as an error.

## Entry Format

Each entry file uses frontmatter + sections:

```markdown
---
id: "NNN"
title: "Descriptive title of the pattern"
problem_type: ci-failure | merge-conflict
trigger_pattern: "exact log string or condition that identifies the problem"
languages: [go, python, yaml, ...]
package_managers: [go-modules, npm, terraform, github-actions, ...]
repos: [org/repo, ...]   # optional: repo-specific patterns only
---

## Problem

What the failure looks like — exact error message or condition.

## Fix

Concrete steps: which files to check, what to change, how to call commit_files.

## Proactive detection   # optional

Pattern that can be detected from the PR diff alone, before CI runs.
Include repo, file path pattern, and what to look for in the diff.

## Example

PR: org/repo#NNN — bumped library old_version → new_version
```

## Matching

When a PR has failing CI or a merge conflict, check loaded entries:

- Compare `trigger_pattern` against `failing_checks[].name` from `get_pr_details`
- Compare `languages` / `package_managers` against `diff_classification`
- For entries with a `repos` field: only match if `pr.repo` is listed

If `## Proactive detection` section is present, also check the diff **before CI runs** — classify as ACTION REQUIRED immediately if the pattern matches.

## Recording New Entries

`/dependabot-fix` records a new entry after a successful fix when:

- The fix is reproducible given the same problem type + language/package manager
- The fix does not depend on repo-specific business logic
- The fix could save time on a future PR

Do **not** record when:
- Fix required understanding of business logic beyond dependency updates
- Fix was specific to one repo's internal structure

### Recording process

1. List `~/.claude/dependabot-fix-knowledge/entries/` to get the next sequential ID
2. Write the new entry file: `entries/NNN-<short-slug>.md`
3. Append one line to `index.md`:
   ```
   - [NNN <title>](entries/NNN-<slug>.md) — <problem_type>: <trigger_pattern>
   ```

## Current Entries

See `~/.claude/dependabot-fix-knowledge/index.md` for the current list. As of the initial documentation:

| ID | Title | Trigger |
|----|-------|---------|
| 001 | SA1019 NewSimpleClientset deprecated in k8s.io/client-go v0.35.0 | `SA1019: k8sfake.NewSimpleClientset is deprecated` |
| 002 | kyma-project/serverless FIPS image bump requires non-FIPS sync | `check-fips-image-versions` |
| 003 | k8s.io/client-go/kubernetes/fake NewClientset populates TypeMeta and ManagedFields | `expected: TypeMeta{Kind:""}  actual: TypeMeta{Kind:"..."}` |
| 004 | Renovate pins internal reusable workflow SHA, breaking GCP OIDC token flow | `Permission 'secretmanager.versions.access' denied` |
| 005 | Terraform action module sources root via git::?ref=main with stale provider constraints | `no available releases match the given constraints ~> X.Y.0, ~> X.Z.0` |
