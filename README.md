# dependabot-reviewer

A Claude Code plugin that automates Dependabot and ospo-renovate PR review across all GitHub hosts you are authenticated with via `gh`. It approves safe updates, flags breaking changes, resolves merge conflicts, and keeps you informed — all without manual triage.

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

See [docs/dependabot-review.md](docs/dependabot-review.md) for the full decision tree and status legend.

### Verify PR status (read-only)

```
/dependabot-verify
```

Scans the same set of PRs and reports their current status without taking any write actions. Useful for a quick overview before running `/dependabot-review`.

See [docs/dependabot-verify.md](docs/dependabot-verify.md) for the classification table and status legend.

### Fix PRs with active problems (read-write)

```
/dependabot-fix [host/org/repo:PR]
```

Finds Dependabot / ospo-renovate PRs with merge conflicts or failing CI. For each problem PR it analyses the root cause, proposes a concrete repair plan, and executes it after your confirmation. Without an argument it scans all open PRs where you are a requested reviewer; a scope argument limits work to a specific host, org, repo, or single PR.

See [docs/dependabot-fix.md](docs/dependabot-fix.md) for the full decision tree and result legend.

### Update branches (read-write)

```
/dependabot-update [host/org/repo:PR]
```

Bulk branch updater: updates all branches that are behind their base and resolves dependency-file merge conflicts (e.g. `go.mod`, `package-lock.json`). Does not approve PRs or post comments. Accepts an optional scope argument to limit work to a specific host, org, repo, or PR.

See [docs/dependabot-update.md](docs/dependabot-update.md) for the status legend and conflict resolution details.

## How it works

The plugin discovers authenticated GitHub hosts via `gh auth status`, then queries each host for open PRs authored by `app/dependabot` or `app/ospo-renovate` where you are a requested reviewer — covering both github.com and GitHub Enterprise Server instances. All GitHub I/O is handled by the bundled `dependabot-reviewer` MCP server, which exposes tools such as `list_dependabot_prs`, `get_pr_details`, `prepare_merge`, and `post_action_required_comment`. The skills orchestrate these tools autonomously and report results in a summary table.

See [docs/README.md](docs/README.md) for a full architecture overview.
