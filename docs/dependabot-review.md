# /dependabot-review — Decision Flow

## Invocation

```
/dependabot-review [<scope>]
```

`<scope>` is optional. Supported formats:

| Format | Effect |
|--------|--------|
| *(none)* | Process all PRs across all authenticated hosts |
| `github.com/org/repo/pull/123` | Single PR (full URL) |
| `https://github.tools.sap/org/repo/pull/123` | Single PR (full HTTPS URL) |
| `github.com/org/repo` | All PRs in one repo on a specific host |
| `github.com/org` | All PRs in one org on a specific host |
| `github.com` | All PRs on a specific host |
| `org/repo:123` or `org/repo#123` | Single PR (default host) |
| `org/repo` | All PRs in one repo (all hosts) |
| `org` | All PRs in one org (all hosts) |

Reviews all open Dependabot/Renovate PRs across all authenticated GitHub hosts. Takes write actions: approves PRs, sets automerge, updates branches, posts comments.

## Decision Tree

```
for each PR
│
├── get_pr_details()
│
├── [Step 3.5] merge_state == "behind"?
│   └── YES → update_branch()
│               ├── "needs_manual_rebase" → 🔄 UPDATED  (stop)
│               └── "done" → get_pr_details() again → continue
│
├── already approved by me AND automerge set?
│   │
│   ├── YES → Path A (already-handled PR)
│   │   │
│   │   ├── merge_state == "dirty"?
│   │   │   └── YES → ⚠️ ACTION REQUIRED (merge conflict)
│   │   │
│   │   └── other merge_state
│   │       └── ci_status == "failing"?
│   │           ├── YES → post_action_required_comment(failing-ci)
│   │           │         → ⚠️ ACTION REQUIRED
│   │           └── NO  → prepare_merge()
│   │                       ├── "done" + branch_updated  → 🔄 UPDATED
│   │                       ├── "done" + !branch_updated → ✅ APPROVED
│   │                       └── "needs_manual_rebase"    → ⚠️ ACTION REQUIRED
│   │
│   └── NO → Path B (new / unhandled PR)
│       │
│       ├── [B1] classify diff_classification
│       │   ├── lock-only
│       │   ├── manifest + patch
│       │   ├── manifest + minor  → changelog available from diff_classification
│       │   └── manifest + major  → changelog available from diff_classification
│       │
│       ├── [B1.5] proactive knowledge base check
│       │   └── pr.repo matches KB entry AND diff matches proactive detection pattern?
│       │       └── YES → post_action_required_comment(breaking-changes, fix steps from KB)
│       │               → ⚠️ ACTION REQUIRED  [skip B2–B5]
│       │
│       ├── [B2] merge_state == "dirty"?
│       │   └── YES → ⚠️ ACTION REQUIRED (merge conflict)
│       │
│       ├── [B2] ci_status == "failing"?
│       │   └── YES → check KB for matching failing_checks
│       │           → post_action_required_comment(failing-ci)
│       │           → ⚠️ ACTION REQUIRED
│       │
│       └── [B3/B4] decision table
│           │
│           ├── lock-only + CI passing                              → APPROVE
│           ├── manifest patch + CI passing                         → APPROVE
│           ├── manifest minor + CI passing + no breaking changes   → APPROVE
│           ├── manifest major + changelog says no breaking changes → APPROVE
│           ├── manifest major (default)                            → ACTION REQUIRED
│           └── changelog has breaking changes / removed APIs       → ACTION REQUIRED
│               │
│               ├── APPROVE → prepare_merge(comment)
│               │               ├── "done" + branch_updated  → 🔄 UPDATED
│               │               ├── "done" + !branch_updated → ✅ APPROVED
│               │               └── "needs_manual_rebase"    → ⚠️ ACTION REQUIRED
│               │
│               └── ACTION REQUIRED → post_action_required_comment()
│                                    → ⚠️ ACTION REQUIRED
```

## Critical Rule: `merge_state == "behind"` is handled in Step 3.5

**`merge_state == "behind"` is resolved in Step 3.5** — before Path A or Path B routing — by calling `update_branch()`. By the time Path A or Path B runs, the branch is guaranteed to be up to date. Neither path contains `"behind"` handling.

This ordering ensures that CI status, changelog analysis, and automerge decisions always run on an up-to-date branch. A failing CI on an outdated branch is meaningless — the real CI result only appears after the branch is updated. Checking CI before updating would produce stale decisions.

## Status Legend

| Symbol | Status | Meaning |
|--------|--------|---------|
| ✅ | `APPROVED` | Approved, automerge set, no branch update needed |
| 🔄 | `UPDATED` | Was already approved; branch was updated or env deployments approved |
| ⚠️ | `ACTION REQUIRED` | Failing CI, breaking changes, or merge conflict; comment left on PR |

## Summary Table Format

```
### <host>

| Repo | PR | Status |
|------|----|--------|
| `org/repo` | [#123](url) | ✅ APPROVED |
| `org/repo` | [#456](url) | 🔄 UPDATED |
| `org/repo` | [#789](url) | ⚠️ ACTION REQUIRED |
```
