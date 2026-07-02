# dependabot-reviewer

A Claude Code plugin that reviews open Dependabot and ospo-renovate PRs where you are a requested reviewer, across all GitHub hosts you are authenticated with via `gh`.

## Prerequisites

- Claude Code with plugin support
- `gh` CLI authenticated to one or more GitHub hosts

## Installation

```
claude plugin marketplace add pPrecel/dependabot-reviewer
claude plugin install dependabot-reviewer@dependabot-reviewer
```

## Usage

### Review PRs (read-write)

```
/dependabot-review
```

Processes all open Dependabot / ospo-renovate PRs where you are a requested reviewer. For each PR it approves safe updates, sets automerge, updates branches, and leaves action-required comments on PRs that need manual attention. Prints a summary table at the end.

### Verify PR status (read-only)

```
/dependabot-verify
```

Scans the same set of PRs and reports their current status without taking any write actions. Useful for a quick overview before running `/dependabot-review`.

## How it works

The plugin discovers all open PRs authored by `app/dependabot` or `app/ospo-renovate` where you are a requested reviewer, across every GitHub host you are authenticated with (`gh auth status`). This covers both github.com and GitHub Enterprise Server instances.

For each PR `/dependabot-review`:

- **approves** and enables automerge for safe updates (lock-only changes, patch/minor bumps with passing CI and no breaking changes in the changelog)
- **updates the branch** if it's behind the base branch, then waits for GitHub to start new CI runs before processing environment approvals
- **approves environment deployments** that are gating CI runs on the updated branch
- **flags** PRs that require manual action — major version bumps, breaking changes in the changelog, or failing CI — and leaves an explanatory comment with details

`/dependabot-verify` classifies each PR into one of: `✅ READY`, `⚠️ ACTION REQUIRED`, `🔄 NEEDS BRANCH UPDATE`, `⏳ WAITING FOR CI`, `👀 NEEDS REVIEW`, or `❌ ERROR`.
