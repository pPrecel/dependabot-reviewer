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

## Step 1: Discover hosts and acquire tokens

```bash
gh auth status --show-token
```

Parse the output to extract every host and its token. Build a list of `{host, token}` pairs — one per authenticated host. Process all of them; do not hardcode any host names.

---

## Step 1.5: Load knowledge base

Read the knowledge base as described in the agent's **Knowledge Base** section. Keep loaded entries available for all subsequent PR processing steps.

---

## Step 2: Discover PRs

For each discovered host, call:

```
list_dependabot_prs(host=<host>, token=<token>)
```

Collect results into one list per host. Each item: `{number, repo, title, url}`.

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

Check `merge_state` from `get_pr_details` first:
- `merge_state == "behind"` → call `prepare_merge` immediately (do not check CI first). If result is `"needs_manual_rebase"` → set status `ACTION REQUIRED` with message. If `"done"` → set status `UPDATED`.
- `merge_state == "dirty"` → set status `ACTION REQUIRED` (merge conflict, cannot update branch).
- Otherwise → check `ci_status`:
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

### Step B1.5: Proactive knowledge base check

**Before checking CI or changelog**, scan the loaded knowledge base entries for any that match this PR based on repo name and diff content:

- For each entry that has a `repos` field: check if `pr.repo` matches one of the listed repos.
- For matching entries, inspect the `## Proactive detection` section (if present) and compare the diff against the described pattern.
- If a match is found → immediately classify as **ACTION REQUIRED** and post a comment using `post_action_required_comment` with:
  - `reason="breaking-changes"`
  - `changelog_excerpt` set to the **Fix** section from the matching KB entry (formatted as the required manual steps)
  - All other fields from `diff_classification`
- Set status `ACTION REQUIRED` and **skip Steps B2–B5** for this PR.

This step catches known repo-specific patterns that require manual action even when CI is green or pending.

### Step B2: Check merge_state and CI

- `merge_state == "behind"` → call `prepare_merge` immediately (do not check CI or changelog). If result is `"needs_manual_rebase"` → ACTION REQUIRED. If `"done"` → status `UPDATED`, stop.
- `merge_state == "dirty"` → ACTION REQUIRED (merge conflict).
- `ci_status == "failing"` → ACTION REQUIRED (even if diff is safe). Before posting the comment, check knowledge base entries for matches on the failing check names and diff classification. If a match is found, include the known root cause and fix steps in the `post_action_required_comment` body.

### Step B3: Read changelog (from PR details)

The changelog is already available in `diff_classification.changelog_excerpt` from the `get_pr_details` result fetched in Step B1. No additional tool call is needed.

- If `changelog_excerpt` is non-empty → use it for breaking-change analysis in Step B4
- If `changelog_excerpt` is empty → treat as no changelog available; apply conservative defaults from decision table

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

Present one table per host after processing all PRs:

### <host>

| Repo | PR | Status |
|------|----|--------|
| `org/repo` | [#123](url) | ✅ APPROVED |
| `org/repo` | [#456](url) | 🔄 UPDATED |
| `org/repo` | [#789](url) | ⚠️ ACTION REQUIRED |

If no PRs found for a host: `No open Dependabot PRs awaiting review on <host>.`

Status legend:
- `✅ APPROVED` — approved, automerge set
- `🔄 UPDATED` — was approved, branch updated or env deployments approved
- `⚠️ ACTION REQUIRED` — failing CI, breaking changes, or merge conflict; comment left on PR
