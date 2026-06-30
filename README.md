# dependabot-reviewer

A Claude Code plugin that reviews open Dependabot PRs where you are a requested reviewer, across both `github.com` and `github.tools.sap`.

## Prerequisites

- Claude Code with plugin support
- `gh` CLI authenticated, or GitHub MCP tools configured in your Claude Code session

## Installation

```
/plugin marketplace add pPrecel/dependabot-reviewer
/plugin install dependabot-reviewer@dependabot-reviewer
```

## Usage

```
/dependabot-review
```

## How it works

The skill fetches all open Dependabot PRs where you are a requested reviewer from both `github.com` and `github.tools.sap`. For each PR it:

- **approves** and enables automerge for safe updates (patch/minor bumps with passing CI and no breaking changes)
- **updates the branch** if it's behind the base branch
- **flags** PRs that require manual action — major version bumps, breaking changes in the changelog, or failing CI — and leaves an explanatory comment

At the end it prints a summary table with the status of every processed PR.
