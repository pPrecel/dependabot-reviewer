---
name: dependabot-review
description: >
  Review all open Dependabot PRs across Otters team repositories.
  Automatically approves safe updates, sets automerge, updates stale branches,
  and leaves analysis comments on PRs that need manual action.
  Invoke with: /dependabot-review
---

# /dependabot-review

You are executing the Dependabot PR review workflow. Work autonomously — do not ask the user for input. Process all PRs and present results at the end.

Use the `dependabot-reviewer` agent for: tooling detection, PR discovery, diff classification, and changelog lookup.

---

## Workflow

### Step 1: Detect tooling

Determine which GitHub API tool is available and has **read-write access** — it must be able to approve PRs, post comments, enable automerge, and update branches. See the `dependabot-reviewer` agent for detection instructions.

Skip `mcp__github-ro__*` and `mcp__github-tools-ro__*` — these are read-only and cannot approve or merge.

### Step 2: Discover PRs

For each host (`github.com` and `github.tools.sap`), run **two queries** and deduplicate by PR number:
1. `review-requested:@me` — PRs not yet reviewed (user still in reviewers list)
2. `reviewed-by:@me` — PRs already reviewed (GitHub removes user from reviewers list after review is submitted)

See the `dependabot-reviewer` agent's "Finding Dependabot PRs" section for exact queries and commands.

Collect results into two lists (one per host). If a host returns an error or no results, note it and continue.

### Step 3: Process each PR

Process PRs sequentially. For each PR:

1. Determine if it is **Path A** or **Path B** (see below).
2. Execute the appropriate path.
3. Record the outcome: `APPROVED`, `UPDATED`, or `ACTION REQUIRED`.

Do not stop on errors for individual PRs — record the error in the status column and continue to the next PR.

---

## Determining Path A vs Path B

**Has existing approve from the current user?**

```bash
gh pr view <number> --repo <owner/repo> --json reviews
# Check reviews[].state == "APPROVED" and reviews[].author.login == current user
```

**Has automerge enabled?**

```bash
gh pr view <number> --repo <owner/repo> --json autoMergeRequest
# autoMergeRequest != null means automerge is set
```

**Path A** (has approve AND automerge set): skip full analysis, go to CI + branch update check.
**Path B** (missing approve or automerge): run full analysis.

---

## Path A: Already-Handled PR

Check CI status:
```bash
gh pr view <number> --repo <owner/repo> --json statusCheckRollup
```
- `statusCheckRollup` contexts: check `state` field — `SUCCESS`, `PENDING`, `FAILURE`, `ERROR`.
- If any check is `FAILURE` or `ERROR` → **ACTION REQUIRED**: leave a comment (see template below), set status `ACTION REQUIRED`.
- If all checks are `SUCCESS` or `PENDING` → check branch staleness.

Check if branch needs update:
```bash
gh pr view <number> --repo <owner/repo> --json mergeable,mergeStateStatus
# mergeStateStatus == "BEHIND" means branch needs update
```

- If `mergeStateStatus == "BEHIND"`:
  ```bash
  gh pr update-branch <number> --repo <owner/repo>
  ```
  Set status: `UPDATED`.
- Otherwise: set status `APPROVED`, no action.

---

## Path B: New / Unhandled PR — Full Analysis

### Step B1: Fetch and classify the diff

Use the `dependabot-reviewer` agent's "Classifying the Diff" section.

### Step B2: Check CI status

```bash
gh pr view <number> --repo <owner/repo> --json statusCheckRollup
```
- Any `FAILURE` or `ERROR` → failing CI
- `SUCCESS` or `PENDING` → not failing

### Step B3: Fetch changelog

Use the `dependabot-reviewer` agent's "Fetching the Changelog" section.

### Step B4: Decision

| Condition | Decision |
|-----------|----------|
| Diff lock-only AND CI not failing AND no breaking changes | **APPROVE** |
| Diff manifest, patch bump AND CI not failing AND no breaking changes | **APPROVE** |
| Diff manifest, minor bump AND CI not failing AND changelog has no breaking changes | **APPROVE** |
| Diff manifest, major bump | **ACTION REQUIRED** (unless changelog explicitly says no breaking changes) |
| CI failing (any check FAILURE/ERROR) | **ACTION REQUIRED** |
| Changelog mentions breaking changes, removed APIs, required migration | **ACTION REQUIRED** |

---

## Actions

### APPROVE action sequence

1. Post approve comment (see template)
2. Approve the PR:
   ```bash
   gh pr review <number> --repo <owner/repo> --approve --body "<comment text>"
   ```
3. Enable automerge:
   ```bash
   gh pr merge <number> --repo <owner/repo> --auto --squash
   ```
   (Use `--squash` as default; if repo requires merge commits use `--merge`.)
4. Approve any pending environment deployments:
   ```bash
   # Get the run ID of the WAITING check (e.g. select-environment)
   gh pr view <number> --repo <owner/repo> --json statusCheckRollup
   # For each run ID with status WAITING, check for pending deployments:
   gh api /repos/<owner/repo>/actions/runs/<run_id>/pending_deployments
   # If current_user_can_approve is true, approve each environment:
   gh api --method POST \
     -H "Accept: application/vnd.github+json" \
     -H "X-GitHub-Api-Version: 2022-11-28" \
     /repos/<owner/repo>/actions/runs/<run_id>/pending_deployments \
     --input - <<< '{"environment_ids": [<env_id>], "state": "approved", "comment": "Approving environment for Dependabot PR"}'
   ```
   Skip this step if there are no WAITING checks.
5. Check and update branch if needed:
   ```bash
   gh pr view <number> --repo <owner/repo> --json mergeStateStatus
   # if BEHIND:
   gh pr update-branch <number> --repo <owner/repo>
   ```
6. Set status: `APPROVED` (or `UPDATED` if branch was updated)

### ACTION REQUIRED action sequence

1. Post analysis comment (see template)
2. Do NOT approve, do NOT set automerge
3. Set status: `ACTION REQUIRED`

---

## Comment Templates

### Approve comment

```
Dependabot PR reviewed ✅

**[library-name]**: v[old] → v[new]
**Type**: [patch | minor | major]

**Changelog**:
> [exact excerpt from release notes — include the full relevant section, not a summary]

Auto-merge enabled.
```

### ACTION REQUIRED comment — failing CI

```
Dependabot PR requires manual action ⚠️

**Reason**: CI checks are failing

**Failing checks**:
| Check | Status |
|-------|--------|
| [check name] | ❌ FAILURE |

**Next steps**: Fix the failing tests or configuration before this PR can be merged. Once fixed, re-run `/dependabot-review` to process this PR.
```

### ACTION REQUIRED comment — breaking changes

```
Dependabot PR requires manual action ⚠️

**Reason**: Breaking changes detected in changelog

**[library-name]**: v[old] → v[new] ([patch | minor | major])

**Relevant changelog excerpt**:
> [exact excerpt mentioning breaking changes, removed APIs, or required migration steps]

**Next steps**: Review the breaking changes above and update the codebase accordingly before approving this PR.
```

---

## Summary Table Format

After processing all PRs, present two tables — one for `github.com`, one for `github.tools.sap`:

### github.com

| Repo | PR | Status |
|------|----|--------|
| `org/repo` | [#123](https://github.com/org/repo/pull/123) | ✅ APPROVED |
| `org/repo` | [#456](https://github.com/org/repo/pull/456) | 🔄 UPDATED |
| `org/repo` | [#789](https://github.com/org/repo/pull/789) | ⚠️ ACTION REQUIRED |

### github.tools.sap

| Repo | PR | Status |
|------|----|--------|
| `org/repo` | [#12](https://github.tools.sap/org/repo/pull/12) | ✅ APPROVED |

If no PRs found for a host, show: `No open Dependabot PRs awaiting review on [host].`

Status legend:
- `✅ APPROVED` — approved, automerge set, branch up to date
- `🔄 UPDATED` — was approved, branch updated to base
- `⚠️ ACTION REQUIRED` — failing CI or breaking changes; comment left on PR
