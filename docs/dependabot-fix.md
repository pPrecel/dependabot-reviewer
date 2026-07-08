# /dependabot-fix — Decision Flow

Fixes a single Dependabot or Renovate problem — either a PR in ACTION REQUIRED state or a repository whose main-branch CI broke after merging a dependency update.

## Invocation

```
/dependabot-fix [host/org/repo:PR]
```

Without an argument, processes all open PRs where you are a requested reviewer.

| Input | Scope |
|-------|-------|
| *(empty)* | all authenticated hosts |
| `<host>` | single host |
| `<org>` | single org across default host |
| `<host>/<org>` | single org on specified host |
| `org/repo` | single repo |
| `<host>/org/repo` | single repo on specified host |
| `org/repo:PR` or `org/repo#PR` | single PR (single mode) |
| Full URL | single PR or repo (host extracted from domain) |

Default host is `github.com`. Single mode is triggered only when a PR number is provided.

## Decision Tree

```
parse argument → {filter_hosts, filter_repo, filter_pr, filter_org, target_type}
acquire tokens via: gh auth status --show-token
load knowledge base from ~/.claude/dependabot-fix-knowledge/
│
├── target_type == "pr" → SINGLE MODE (specific PR)
│   └── [proceed to PR analysis below]
│
├── target_type == "repo" → SINGLE MODE (repo main branch)
│   └── [proceed to repo analysis below]
│
└── target_type == "bulk" → BULK MODE
    │
    ├── list_dependabot_prs() with applicable scope filter
    │   └── empty list → "No open Dependabot PRs matching the given filter." → stop
    │
    └── for each PR:
        ├── get_pr_details()
        ├── merge_state != "dirty" AND ci_status != "failing" → skip silently
        └── proceed to PR analysis below
            └── after Step 7 → record result → continue to next PR
    └── print summary table

── PR analysis ─────────────────────────────────────────────────────────────

├── get_pr_details()
│
├── merge_state == "dirty"?  → merge conflict present
├── ci_status == "failing"?  → failing CI present
│
├── both problems → address conflict first, then CI
├── neither       → "no active problem detected" → skip to proposal
│
├── [if CI failing] get_check_logs() for each failing check
├── [if conflict]   get_raw_diff() → find <<<<<<< markers
│
└── match against KB entries

── Repo analysis (target_type == "repo", single mode only) ─────────────────

├── get_branch_ci_status(branch="main")
│   └── 404 → retry with "master"
│
├── ci_status != "failing" → "Main branch CI is not failing" → stop
│
├── get_check_logs() for each failing check
├── list_recently_merged_dependabot_prs(since = today - 14 days)
│   └── correlate merge timestamps with first CI failure
│
└── match against KB entries
    └── root cause NOT from dependency update? → scope check error → stop
```

## Repair Approach Selection

| Problem | Approach |
|---------|----------|
| CI failing on PR branch | Commit fix directly to PR branch |
| Merge conflict on PR branch | Commit resolved conflicts to PR branch |
| CI failing on main after merge | Create patch branch + open PR to main/master |
| Complex API migration on PR branch | Commit migration fix to PR branch |
| Infrastructure problem (GCP IAM, CI runner) | Post diagnostic comment only |

## Execution Flow

```
[proposed plan] → await user confirmation (tak/yes/empty = proceed)
│
├── fix merge conflict (if applicable)
│   ├── get_file_contents() for each conflicted file from PR branch + base
│   ├── resolve: dependency files → Dependabot/Renovate version wins
│   ├── get_pr_head_sha()
│   └── commit_files(message="fix: resolve merge conflicts [dependabot skip]")
│
├── fix failing CI (if applicable)
│   ├── get_file_contents() for affected files
│   ├── apply fix
│   ├── get_pr_head_sha()  ← always re-fetch after any commit
│   └── commit_files(message="fix: resolve CI failure in <check> [dependabot skip]")
│
└── main branch case
    ├── get_branch_head_sha(branch="main")
    ├── commit_files(branch="fix/dependabot-ci-<desc>")  ← creates new branch
    └── create_pull_request(head="fix/...", base="main")
```

## Summary Table (bulk mode only)

Printed after all PRs are processed:

```
| Repo | PR | Title | Status | Detail |
|------|----|-------|--------|--------|
| org/repo | [#123](url) | Bump foo 1.0→2.0 | ✅ FIXED | <commit_url> |
| org/repo | [#456](url) | Bump bar 3.1→3.2 | ⏭️ SKIPPED (user) | |
| org/repo | [#789](url) | Bump baz 0.1→0.2 | ❌ FAILED | Step 6d: file not found |
| org/repo | [#101](url) | Bump qux 5.0→6.0 | 💬 DIAGNOSTIC COMMENT | <comment_url> |
```

| Status | Meaning |
|--------|---------|
| `✅ FIXED` | Repair executed successfully |
| `⏭️ SKIPPED (user)` | User replied `no` to confirmation prompt |
| `❌ FAILED` | Step 6d triggered and not resolved |
| `💬 DIAGNOSTIC COMMENT` | Infrastructure problem; diagnostic comment posted |

## Branch Creation Note

On **github.tools.sap** (GHE) and **github.com**, `commit_files` via GraphQL `createCommitOnBranch` does NOT auto-create new branches. Always pre-create the branch via REST before calling `commit_files`:

```bash
gh api --hostname <host> \
  -X POST repos/<org>/<repo>/git/refs \
  -f ref="refs/heads/<branch-name>" \
  -f sha="<head-sha>"
```

## Post-execution

After a successful fix:
1. Post success comment on the PR with commit URL and KB entry used
2. Evaluate if the fix is generic enough to record in the knowledge base (see [knowledge-base.md](knowledge-base.md))

After an unfixable/infrastructure problem:
1. Post diagnostic comment with investigation details and manual action steps
