# Design: Extract Changelog from PR Body

**Date:** 2026-07-02
**Status:** Approved

## Problem

The MCP server currently has a `get_changelog` tool that fetches release notes from GitHub Releases or CHANGELOG.md for a given library. This is unnecessary because both dependabot and ospo-renovate already embed changelog/release notes directly in the PR body. Fetching them separately adds latency, complexity, and an extra tool call.

## Goal

Remove `get_changelog` from the MCP server. Instead, extract the changelog excerpt from the PR body inside `get_pr_details` and return it as part of `PRDetails`. The skill reads `changelog_excerpt` from the already-fetched PR details — no extra tool call needed.

## PR Body Formats Observed

| Bot | Scenario | Body content |
|-----|----------|-------------|
| dependabot | commit hash / digest bump | commit list + compare link only — no release notes |
| dependabot | patch/minor with changelog | HTML `<blockquote>` under `Release notes` and/or `Changelog` headings |
| ospo-renovate | digest update | table only, no Release Notes section |
| ospo-renovate | version bump, no notes | `### Release Notes` heading with only compare links |
| ospo-renovate | version bump with notes | `### Release Notes` heading with full Markdown content |

## Changes

### 1. New module: `body_parser.py`

Single public function:

```python
def extract_changelog(body: str) -> str
```

Logic:
1. Look for `### Release Notes` section (renovate Markdown format) — extract everything between that heading and the next `---` separator or end of string.
2. Look for `Release notes` or `Changelog` HTML blockquote (dependabot format) — extract text content from `<blockquote>...</blockquote>` after the relevant heading.
3. Strip HTML tags and decode HTML entities to produce plain text.
4. Truncate to 2000 characters to avoid flooding the skill's context.
5. If no section found → return `""`.

### 2. `models.py`

Add field to `PRDetails`:
```python
changelog_excerpt: str  # empty string if not present in PR body
```

Remove `Changelog` model entirely (no longer used).

### 3. `server.py`

In `get_pr_details`:
- Call `extract_changelog(pr["body"] or "")` and set `changelog_excerpt` in `PRDetails`.

Remove `get_changelog` tool function entirely.

### 4. `github_client.py`

Remove methods used only by `get_changelog`:
- `get_release(repo, tag)`
- `get_file(repo, path)`

### 5. `skills/dependabot-review/SKILL.md`

Replace Step B3 (fetch changelog):

**Before:**
> Derive `library_repo` from the PR diff or title and call `get_changelog(...)`.

**After:**
> Read `diff_classification.changelog_excerpt` from the `get_pr_details` result already fetched in Step B1. No additional tool call needed.

Decision table (Step B4) and comment templates are unchanged.

## What Does NOT Change

- `classifier.py` — diff classification logic unchanged
- `prepare_merge`, `post_action_required_comment` tools — unchanged
- `dependabot-verify` skill — unchanged (does not use changelog at all)
- Decision table in `dependabot-review` skill — unchanged

## Testing

- Unit tests for `body_parser.extract_changelog` covering:
  - dependabot HTML blockquote (Release notes section)
  - dependabot HTML blockquote (Changelog section)
  - renovate Markdown `### Release Notes` with full content
  - renovate `### Release Notes` with only compare links → returns `""`
  - body with no release notes section → returns `""`
  - body is `None` or empty → returns `""`
- Existing tests for `get_pr_details` updated to include `changelog_excerpt` field.
