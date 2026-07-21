---
name: dependabot-babysit
description: >
  Loop until all Dependabot/Renovate PRs are merged and main branches are passing.
  Runs verify → main health check → review → fix cycles at a configurable interval.
  Asks for confirmation before each fix attempt. Stops automatically when done.
  Invoke with: /dependabot-babysit [interval] [scope]
---

# /dependabot-babysit

Drive all Dependabot/Renovate PRs to merged state with healthy main branches.
Runs in a loop — invoke once and it keeps cycling until everything is done.

**Requires:** the `/loop` built-in skill must be available in the current Claude Code
session. If it is not present, stop and report: `"Error: /loop skill not found. /dependabot-babysit requires the bundled loop skill."`

---

## Step 0: Parse arguments

Parse `ARGUMENTS` (text after the skill name). Extract two optional values:

| Variable   | Type            | Description |
|------------|-----------------|-------------|
| `interval` | `string \| null` | Loop interval passed to `/loop` (e.g. `15m`, `30m`, `1h`). Default: `15m`. |
| `scope`    | `string \| null` | Scope forwarded to each cycle (host, org, org/repo, etc.). `null` = all hosts. |

### Parsing rules

Scan tokens in `ARGUMENTS` left to right:

1. A token matching `^\d+[smhd]$` (digits followed by s/m/h/d) → `interval` (first match only; subsequent matching tokens are treated as part of `scope`)
2. All remaining tokens joined with a space → `scope` (or `null` if nothing remains)

Examples:

| ARGUMENTS              | `interval` | `scope`       |
|------------------------|------------|---------------|
| *(empty)*              | `15m`      | null          |
| `30m`                  | `30m`      | null          |
| `20m myorg`            | `20m`      | `myorg`       |
| `github.com/myorg`     | `15m`      | `github.com/myorg` |
| `1h myorg/myrepo`      | `1h`       | `myorg/myrepo` |

---

## Step 1: Write state file

Write `~/.claude/dependabot-babysit-state.json` with initial state:

```json
{
  "blocked_prs": [],
  "blocked_repos": [],
  "iteration": 0,
  "start_time": "<current ISO 8601 timestamp>",
  "scope": "<scope or null>"
}
```

Use the current wall-clock time for `start_time`.

If the file already exists (a previous babysit session for the same scope), read it and
**preserve** `blocked_prs`, `blocked_repos`, and `start_time`. Reset `iteration` to 0 only
if `scope` has changed. This allows resuming an interrupted session. If `scope` has changed,
also clear `blocked_prs` and `blocked_repos` — blocked state from a different scope is not applicable.

---

## Step 2: Launch loop

Invoke the `/loop` skill:

```
/loop <interval> /dependabot-babysit-cycle <scope>
```

Where:
- `<interval>` is the value from Step 0 (default `15m`)
- `<scope>` is the scope from Step 0, appended only if non-null

Examples:
```
/loop 15m /dependabot-babysit-cycle
/loop 30m /dependabot-babysit-cycle myorg
/loop 1h /dependabot-babysit-cycle github.com/myorg
```

After invoking the loop, print:

```
Babysit started. Cycling every <interval>.
State file: ~/.claude/dependabot-babysit-state.json
Stop condition: all eligible PRs merged + all main branches passing.
To stop early: cancel the /loop manually.
```

The `/loop` skill takes over from here. Each cycle runs `/dependabot-babysit-cycle`.
