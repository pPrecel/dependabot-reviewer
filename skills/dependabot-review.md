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

Use the `dependabot-reviewer` agent for domain knowledge on diff interpretation, changelog lookup, and decision logic.

---

## Workflow

### Step 1: Detect tooling

Determine which GitHub API tool is available (MCP tools → gh CLI → curl). See the `dependabot-reviewer` agent for detection instructions.

### Step 2: Discover PRs

Fetch all open Dependabot PRs where the current user is a requested reviewer, from both:
- `github.com`
- `github.tools.sap`

Collect results into two lists (one per host). If a host returns an error or no results, note it and continue.

### Step 3: Process each PR

Process PRs sequentially. For each PR:

1. Determine if it is **Path A** (already has approve + automerge) or **Path B** (needs full analysis). See `dependabot-reviewer` agent for how to check.
2. Execute the appropriate path as described in the `dependabot-reviewer` agent.
3. Record the outcome: `APPROVED`, `UPDATED`, or `ACTION REQUIRED`.

Do not stop on errors for individual PRs — record the error in the status column and continue to the next PR.

### Step 4: Present summary tables

After all PRs are processed, display two tables — one for `github.com`, one for `github.tools.sap` — using the format defined in the `dependabot-reviewer` agent.

If no PRs were found on either host, say so explicitly.
