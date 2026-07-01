# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A Claude Code plugin that automates Dependabot PR review. It provides:

- **`/dependabot-review` skill** (`skills/dependabot-review/SKILL.md`) — reviews PRs: approves safe updates, sets automerge, updates branches, leaves analysis comments
- **`/dependabot-verify` skill** (`skills/dependabot-verify/SKILL.md`) — read-only status check: scans PRs and reports their state without taking any write actions
- **`dependabot-reviewer` agent** (`agents/dependabot-reviewer.md`) — shared domain knowledge used by both skills

The plugin is declared in `.claude-plugin/plugin.json`.

## Versioning

When bumping the version, **always update both files together**:
- `.claude-plugin/plugin.json` — `version` field
- `.claude-plugin/marketplace.json` — `version` field inside `plugins[0]`

Both must always be in sync.

## Architecture

### Separation of concerns (enforced)

**Agent** (`agents/dependabot-reviewer.md`) contains **only shared domain knowledge**:
- GitHub API tooling detection (generic, not tied to read-only or read-write)
- PR discovery queries (the `is:open is:pr author:app/dependabot review-requested:@me` pattern for both hosts)
- Diff classification (lock-only vs manifest, semver bump logic)
- Changelog lookup (GitHub Releases → CHANGELOG.md → package registry)

**Skills** contain **only their own workflow logic**:
- `dependabot-review/SKILL.md` — Path A/B routing, decision table, APPROVE/ACTION REQUIRED action sequences, comment templates, summary table format (APPROVED/UPDATED/ACTION REQUIRED)
- `dependabot-verify/SKILL.md` — tooling detection with read-only preference, classification priority table (7 states), summary table format with Detail column

**Rule**: if logic is used by only one skill, it belongs in that skill. If logic is used by both skills (or is general Dependabot/GitHub domain knowledge), it belongs in the agent.

### File paths

```
agents/dependabot-reviewer.md   ← shared domain knowledge
skills/dependabot-review/SKILL.md  ← review workflow
skills/dependabot-verify/SKILL.md  ← verify (read-only) workflow
.claude-plugin/plugin.json      ← plugin declaration
```

### MCP server (`mcp-server/`)

The plugin ships a Python MCP server that owns all GitHub I/O for the `dependabot-review` skill. It exposes 5 tools:

- `list_dependabot_prs(host, token)` — discover PRs via `@me` search qualifiers
- `get_pr_details(host, token, repo, pr_number)` — fetch reviews, CI, diff, comments in parallel
- `get_changelog(host, token, library_repo, new_version)` — fetch release notes
- `prepare_merge(host, token, repo, pr_number, comment)` — orchestrate rebase → env approvals → automerge → approve
- `post_action_required_comment(host, token, repo, pr_number, reason, ...)` — post structured comment

The server is declared in `.mcp.json`. Token acquisition (`gh auth token`) stays in the skill — the server is stateless and receives `host` and `token` on every call.

Source: `mcp-server/dependabot_mcp/`
Tests: `mcp-server/tests/`

## Key design decisions

**Tooling detection order**: MCP tools → `gh` CLI → `curl`. The agent describes detection generically. Each skill specifies its own access requirements: `dependabot-review` requires read-write access; `dependabot-verify` prefers read-only MCP tools and does not require write access.

**Path A vs Path B** (review only): PRs that already have both an approve from the current user and automerge set skip full analysis (Path A: CI check + branch update only). All other PRs get full analysis (Path B). This routing logic lives in `dependabot-review/SKILL.md`, not in the agent.

**Approval decision**: lock-only diffs and patch/minor bumps without breaking changelog entries are auto-approved. Major bumps or failing CI always require manual action. Decision table lives in `dependabot-review/SKILL.md`.

**Two-host processing**: both skills always query `github.com` and `github.tools.sap` and present separate result tables per host.

**dependabot-verify is strictly read-only**: it must never approve, comment, set automerge, update branches, or approve environment deployments.
