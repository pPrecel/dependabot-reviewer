# /dependabot-fix — Decision Flow

Fixes a single Dependabot or Renovate problem — either a PR in ACTION REQUIRED state or a repository whose main-branch CI broke after merging a dependency update.

## Invocation

```
/dependabot-fix [host] <ref>
```

Supported `<ref>` formats:

| Format | Example |
|--------|---------|
| Full URL (PR) | `https://github.com/org/repo/pull/123` |
| Full URL (repo) | `https://github.com/org/repo` |
| Explicit host + PR | `github.tools.sap org/repo#123` |
| Explicit host + repo | `github.tools.sap org/repo` |
| Default host PR | `org/repo#123` |
| Default host repo | `org/repo` |

Default host is `github.com`.

## Decision Tree

```
parse argument → {host, target_type, repo, [pr_number]}
acquire token via: gh auth status --show-token
load knowledge base from ~/.claude/dependabot-fix-knowledge/
│
├── target_type == "pr"
│   │
│   ├── get_pr_details()
│   │
│   ├── merge_state == "dirty"?  → merge conflict present
│   ├── ci_status == "failing"?  → failing CI present
│   │
│   ├── both problems → address conflict first, then CI
│   ├── neither       → "no active problem detected" → skip to proposal
│   │
│   ├── [if CI failing] get_check_logs() for each failing check
│   ├── [if conflict]   get_raw_diff() → find <<<<<<< markers
│   │
│   └── match against KB entries
│
└── target_type == "repo"
    │
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
