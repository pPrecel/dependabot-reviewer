# dependabot-reviewer — Overview

This plugin automates Dependabot and Renovate PR review for Claude Code. It ships three skills and one shared MCP server.

## Skills

| Skill                                        | Invocation                         | Access     | Purpose                                                                                         |
|----------------------------------------------|------------------------------------|------------|-------------------------------------------------------------------------------------------------|
| [`/dependabot-review`](dependabot-review.md) | `/dependabot-review [scope]`       | read-write | Review all open PRs: approve, set automerge, update branches, post ACTION REQUIRED comments     |
| [`/dependabot-verify`](dependabot-verify.md) | `/dependabot-verify [scope]`       | read-only  | Report status of all open PRs without taking any write actions                                  |
| [`/dependabot-fix`](dependabot-fix.md)       | `/dependabot-fix [--yes] [scope]`  | read-write | Fix PRs or repos with merge conflicts or failing CI; bulk or single mode                        |
| [`/dependabot-update`](dependabot-update.md) | `/dependabot-update [scope]`       | read-write | Update all open PR branches: rebase behind branches and resolve dependency-file merge conflicts |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Claude Code session                  │
│                                                         │
│  /dependabot-review   /dependabot-verify   /dependabot-fix   /dependabot-update │
│         │                    │                   │       │
│         └────────────────────┴───────────────────┘       │
│                              │                           │
│                    MCP server calls                      │
└──────────────────────────────┼──────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │   dependabot-reviewer MCP server  │
              │   (Python, mcp-server/)           │
              │                                   │
              │  list_dependabot_prs              │
              │  get_pr_details                   │
              │  get_changelog                    │
              │  prepare_merge                    │
              │  update_branch                    │
              │  post_action_required_comment     │
              │  get_branch_ci_status             │
              │  get_check_logs                   │
              │  list_recently_merged_...         │
              │  commit_files                     │
              │  create_pull_request              │
              │  get_branch_head_sha              │
              │  get_file_contents                │
              │  get_pr_head_sha                  │
              │  get_raw_diff                     │
              └──────────────────────────────────┘
                               │
                     GitHub API (REST + GraphQL)
                  github.com, github.tools.sap, ...
```

## Shared Knowledge Base (Cache)

All three skills share a persistent knowledge base at `~/.claude/dependabot-fix-knowledge/`. See [knowledge-base.md](knowledge-base.md) for the full description.

## Multi-host Support

Every skill discovers all authenticated GitHub hosts by running:

```bash
gh auth status --show-token
```

Each `{host, token}` pair found is processed independently. Results are presented in separate tables per host. No host names are hardcoded.

## Token Flow

The MCP server is stateless — it receives `host` and `token` on every call. Token acquisition (`gh auth status`) always happens in the skill, never inside the server.
