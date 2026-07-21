# /dependabot-babysit — Decision Flow

Drives all Dependabot/Renovate PRs to merged state with healthy main branches.
Runs a verify → main health check → review/update → fix cycle on a configurable interval.
Stops automatically when all eligible PRs are merged and all main branches are passing.

## Invocation

```
/dependabot-babysit [interval] [scope]
```

| Argument   | Default | Description |
|------------|---------|-------------|
| `interval` | `15m`   | Loop interval (e.g. `15m`, `30m`, `1h`) |
| `scope`    | all hosts | Same format as other skills: host, org, org/repo |

Examples:
```
/dependabot-babysit
/dependabot-babysit 30m
/dependabot-babysit 20m myorg
/dependabot-babysit github.com/myorg
```

## Decision Tree (per iteration)

```
load state (~/.claude/dependabot-babysit-state.json)
│
├── verify: list all open PRs + main branch CI status
│
├── Step 3: main branch health (PRIORITY — runs before review)
│   └── for each repo with failing main (not in blocked_repos):
│       ├── check if failure is caused by recent Dependabot merge
│       │   └── not dependency-related → skip (out of scope, do not gate review)
│       ├── yes → confirm with user → /dependabot-fix --yes <repo>
│       │         fail/decline → add to blocked_repos
│       └── build unhealthy_repos: repos still failing and not blocked
│
├── Step 4: review / update (skips PRs in blocked_prs or unhealthy_repos)
│   ├── NEEDS REVIEW → /dependabot-review (full Path B analysis + prepare_merge)
│   ├── NEEDS BRANCH UPDATE → update_branch + conflict resolution if needed
│   ├── WAITING FOR CI → no action
│   ├── READY → no action (GitHub automerge pending)
│   └── ACTION REQUIRED → deferred to Step 5
│
├── Step 5: fix ACTION REQUIRED PRs (skips blocked_prs + unhealthy_repos)
│   └── for each PR:
│       ├── present diagnosis → confirm with user
│       ├── yes → /dependabot-fix --yes <repo>:<pr>
│       │         fail → add to blocked_prs
│       └── no → add to blocked_prs
│
├── Step 6: stop condition
│   ├── no open eligible PRs AND all eligible mains passing → final report → exit
│   └── otherwise → iteration report → /loop schedules next cycle
│
└── save state file
```

## Stop Condition

The skill exits when **all** of the following are true:

- No open PRs remain outside `blocked_prs` (all were merged by GitHub)
- All repos outside `blocked_repos` have main branch CI `✅ passing`

Because `/loop` runs autonomously, after printing the final report the skill will be
invoked one more time and will exit silently with "nothing to do". Stop `/loop` manually.

## Session State

State is persisted between loop cycles in `~/.claude/dependabot-babysit-state.json`:

| Field | Description |
|-------|-------------|
| `blocked_prs` | PRs where fix failed or user declined. Never retried in this session. |
| `blocked_repos` | Repos where main branch fix failed or user declined. Skipped in all subsequent cycles. |
| `iteration` | Current cycle count. |
| `start_time` | ISO timestamp of first invocation (used in elapsed-time calculation). |
| `scope` | Scope argument, forwarded to each cycle. |

## Status Legend (iteration report)

### PRs

| Status | Meaning |
|--------|---------|
| ✅ merged | PR was closed/merged by GitHub |
| ✅ READY | Approved, automerge set, waiting for GitHub to merge |
| ⚠️ ACTION REQUIRED | CI failing, merge conflict, or breaking change |
| 🔄 NEEDS BRANCH UPDATE | Branch behind base |
| ⏳ WAITING FOR CI | Checks still running |
| 👀 NEEDS REVIEW | Not yet reviewed |
| 🔒 skipped | PR's repo has a failing main; deferred |

### Main branches

| Status | Meaning |
|--------|---------|
| ✅ passing | CI green, no action needed |
| ❌ failing | CI failing (see Action column for what was done) |
| ⏳ pending | CI still running |
| ❓ unknown | Status could not be determined |
| ❌ ERROR | API call failed |
