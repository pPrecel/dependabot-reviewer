# /dependabot-verify — Decision Flow

Read-only scan of all open Dependabot/Renovate PRs. Reports status without taking any write actions. Never approves, comments, sets automerge, updates branches, or approves environment deployments.

## Decision Tree

```
for each PR
│
├── get_pr_details()
│
├── [Priority 0] KB proactive match?
│   └── pr.repo in KB entry's repos field
│       AND diff matches ## Proactive detection pattern?
│       └── YES → ⚠️ ACTION REQUIRED
│               Detail: "known pattern: <entry title>"
│
├── [Priority 1] ci_status == "failing"?
│   OR any comment contains "requires manual action ⚠️"?
│   └── YES → ⚠️ ACTION REQUIRED
│           Detail: list of failing check names
│                   + "(known pattern: <title>)" if KB match
│
├── [Priority 2] merge_state == "behind"?
│   └── YES → 🔄 NEEDS BRANCH UPDATE
│           Detail: "branch is behind <base-branch>"
│
├── [Priority 3] ci_status == "pending"?
│   └── YES → ⏳ WAITING FOR CI
│           Detail: "<N> checks pending"
│
├── [Priority 4] no APPROVED review from current user
│               AND no comment with "Dependabot PR reviewed ✅"
│               AND no comment with "requires manual action ⚠️"?
│   └── YES → 👀 NEEDS REVIEW
│           Detail: "no review yet"
│
├── [Priority 5] approved by current user
│               AND auto_merge_set == true
│               AND ci_status == "passing"
│               AND merge_state != "behind"?
│   └── YES → ✅ READY
│           Detail: —
│
└── [Priority 6] catch-all
    └── 👀 NEEDS REVIEW
        Detail: "needs attention"
```

## Main Branch Health Check (Step 5)

After classifying all open PRs, the skill also checks the default branch CI status for every repo that had an open or recently-merged Dependabot PR:

```
collect unique repos from:
  ├── open PR list (Step 2)
  └── list_recently_merged_dependabot_prs(since = today - 7 days)

for each (host, repo):
  └── get_branch_ci_status(branch="main")
      ├── 404 → retry with branch="master"
      └── present in health table
```

Health table:

```
#### Main branch health — <host>

| Repo | Branch | Status | Failing checks |
|------|--------|--------|----------------|
| `org/repo` | main | ✅ passing | — |
| `org/repo` | main | ❌ failing | build, lint |
| `org/repo` | main | ⏳ pending | — |
```

## Status Legend

| Symbol | Status | Meaning |
|--------|--------|---------|
| ✅ | `READY` | Approved, automerge set, CI green, branch up to date |
| ⚠️ | `ACTION REQUIRED` | Failing CI or prior ACTION REQUIRED comment; manual intervention needed |
| 🔄 | `NEEDS BRANCH UPDATE` | Branch is behind base; needs update before merge |
| ⏳ | `WAITING FOR CI` | Checks still running; no action needed yet |
| 👀 | `NEEDS REVIEW` | Not yet reviewed or analysed |
| ❌ | `ERROR` | Failed to fetch PR data |

## Summary Table Format

```
#### <host>

| Repo | PR | Status | Detail |
|------|----|--------|--------|
| `org/repo` | [#123](url) | ✅ READY | — |
| `org/repo` | [#456](url) | ⚠️ ACTION REQUIRED | CI: test-unit FAILURE |
| `org/repo` | [#789](url) | ⏳ WAITING FOR CI | 3 checks pending |
| `org/repo` | [#102](url) | 🔄 NEEDS BRANCH UPDATE | branch is behind main |
| `org/repo` | [#103](url) | 👀 NEEDS REVIEW | no review yet |
```
