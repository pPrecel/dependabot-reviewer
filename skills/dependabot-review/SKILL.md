---
name: dependabot-review
description: >
  Review all open Dependabot PRs across Otters team repositories.
  Automatically approves safe updates, sets automerge, updates branches,
  and leaves analysis comments on PRs that need manual action.
  Invoke with: /dependabot-review
---

# /dependabot-review

You are executing the Dependabot PR review workflow. Work autonomously — do not ask the user for input. Process all PRs and present results at the end.

All GitHub I/O is performed through the `dependabot-reviewer` MCP server tools. Do not call `gh` CLI for any GitHub operations — only for token acquisition.

---

## Step 1: Acquire tokens

```bash
TOKEN_GH=$(gh auth token)
TOKEN_SAP=$(GH_HOST=github.tools.sap gh auth token 2>/dev/null || echo "")
```

If `TOKEN_SAP` is empty, skip `github.tools.sap` processing and note it in the summary.

---

## Step 2: Discover PRs

For each host that has a token, call:

```
list_dependabot_prs(host="github.com", token=TOKEN_GH)
list_dependabot_prs(host="github.tools.sap", token=TOKEN_SAP)   # if token available
```

Collect results into two lists. Each item: `{number, repo, title, url}`.

---

## Step 3: Process each PR

Process PRs sequentially. For each PR call:

```
get_pr_details(host, token, repo=pr.repo, pr_number=pr.number)
```

Use the returned data to determine **Path A** or **Path B**.

---

## Determining Path A vs Path B

**Path A** — PR already has an APPROVED review from the current user AND automerge is set:
- `reviews` contains an entry with `state == "APPROVED"` from you
- `auto_merge_set == true`

**Path B** — missing approve OR automerge not set: run full analysis.

---

## Path A: Already-Handled PR

Check `ci_status` from `get_pr_details`:
- `ci_status == "failing"` → call `post_action_required_comment` (reason: `"failing-ci"`), set status `ACTION REQUIRED`
- Otherwise → call `prepare_merge`. If result is `"needs_manual_rebase"` → set status `ACTION REQUIRED` with message. If `"done"` → set status `UPDATED` if `branch_updated` else `APPROVED`.

---

## Path B: New / Unhandled PR — Full Analysis

### Step B1: Classify

Use `diff_classification` from `get_pr_details`:
- `type == "lock-only"` → safe, no changelog needed
- `type == "manifest"` + `semver == "patch"` → safe, no changelog needed
- `type == "manifest"` + `semver == "minor"` → fetch changelog
- `type == "manifest"` + `semver == "major"` → fetch changelog, likely ACTION REQUIRED

### Step B2: Check CI

- `ci_status == "failing"` → ACTION REQUIRED (even if diff is safe)

### Step B3: Fetch changelog (if needed)

Derive `library_repo` from the PR diff or title:
- For Go modules like `github.com/foo/bar` → `library_repo = "foo/bar"`
- For npm packages with a known GitHub repo → use the repo URL from package metadata
- For packages where the GitHub repo cannot be determined → skip changelog, treat as no breaking changes

```
get_changelog(host, token, library_repo=..., new_version=pr.diff_classification.new_version)
```

### Step B4: Decision table

| Condition | Decision |
|-----------|----------|
| lock-only AND CI passing | APPROVE |
| manifest, patch AND CI passing | APPROVE |
| manifest, minor AND CI passing AND changelog has no breaking changes | APPROVE |
| manifest, major AND changelog explicitly says no breaking changes | APPROVE |
| manifest, major (default) | ACTION REQUIRED |
| CI failing | ACTION REQUIRED |
| Changelog mentions breaking changes, removed APIs, required migration | ACTION REQUIRED |

### Step B5: Execute decision

**APPROVE:**

Build the comment body:
```
Dependabot PR reviewed ✅

**[library]**: v[old] → v[new]
**Type**: [patch | minor | major]

**Changelog**:
> [changelog excerpt, or "No changelog found." if not available]

Auto-merge enabled.
```

Then call:
```
prepare_merge(host, token, repo, pr_number, comment=<body above>)
```

- `"done"` → status `APPROVED` (or `UPDATED` if `branch_updated`)
- `"needs_manual_rebase"` → status `ACTION REQUIRED`, note merge conflict

**ACTION REQUIRED:**

```
post_action_required_comment(
  host, token, repo, pr_number,
  reason="failing-ci" | "breaking-changes",
  failing_checks=...,     # from get_pr_details.failing_checks
  library=..., old_version=..., new_version=..., semver=...,
  changelog_excerpt=...   # for breaking-changes only
)
```

Set status `ACTION REQUIRED`.

---

## Summary Table

Present two tables after processing all PRs:

### github.com

| Repo | PR | Status |
|------|----|--------|
| `org/repo` | [#123](url) | ✅ APPROVED |
| `org/repo` | [#456](url) | 🔄 UPDATED |
| `org/repo` | [#789](url) | ⚠️ ACTION REQUIRED |

### github.tools.sap

| Repo | PR | Status |
|------|----|--------|
| `org/repo` | [#12](url) | ✅ APPROVED |

If no PRs found for a host: `No open Dependabot PRs awaiting review on [host].`

Status legend:
- `✅ APPROVED` — approved, automerge set
- `🔄 UPDATED` — was approved, branch updated or env deployments approved
- `⚠️ ACTION REQUIRED` — failing CI, breaking changes, or merge conflict; comment left on PR
