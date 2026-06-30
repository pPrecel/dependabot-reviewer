# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A Claude Code plugin that automates Dependabot PR review. It provides:

- **`/dependabot-review` skill** (`skills/dependabot-review.md`) — the slash command users invoke to trigger the workflow
- **`dependabot-reviewer` agent** (`agents/dependabot-reviewer.md`) — domain knowledge agent used by the skill for diff interpretation, changelog lookup, and approval decisions

The plugin is declared in `.claude-plugin/plugin.json`.

## Architecture

The workflow is split across two files intentionally:

- `skills/dependabot-review.md` — orchestration only: detects tooling, discovers PRs from both `github.com` and `github.tools.sap`, processes each PR sequentially, and renders the final summary table.
- `agents/dependabot-reviewer.md` — all domain logic: GitHub API tooling detection, Path A vs Path B routing, diff classification, changelog lookup, approval decision table, action sequences, and comment templates.

The skill delegates to the agent for any decision logic. Keep these concerns separated when editing.

## Key design decisions

**Tooling detection order**: MCP tools → `gh` CLI → `curl`. The agent always auto-detects — never prompts the user. MCP tools may only cover `github.com`; `github.tools.sap` falls back to `gh --hostname github.tools.sap`.

**Path A vs Path B**: PRs that already have both an approve from the current user and automerge set skip full analysis (Path A: CI check + branch update only). All other PRs get full analysis (Path B).

**Approval decision**: lock-only diffs and patch/minor bumps without breaking changelog entries are auto-approved. Major bumps or failing CI always require manual action.

**Two-host processing**: the skill always queries both `github.com` and `github.tools.sap` and presents separate result tables per host.
