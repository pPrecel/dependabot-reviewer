# dependabot-reviewer

A Claude Code plugin that reviews open Dependabot PRs where you are a requested reviewer, across all GitHub hosts you are authenticated with via `gh`.

## Prerequisites

- Claude Code with plugin support
- `gh` CLI authenticated to one or more GitHub hosts

## Installation

```
claude plugin marketplace add pPrecel/dependabot-reviewer
claude plugin install dependabot-reviewer@dependabot-reviewer
```

## Usage

```
/dependabot-review
```

## How it works

The skill fetches all open Dependabot PRs where you are a requested reviewer from all GitHub hosts you are authenticated with. For each PR it:

- **approves** and enables automerge for safe updates (patch/minor bumps with passing CI and no breaking changes)
- **updates the branch** if it's behind the base branch
- **flags** PRs that require manual action — major version bumps, breaking changes in the changelog, or failing CI — and leaves an explanatory comment

At the end it prints a summary table with the status of every processed PR.
