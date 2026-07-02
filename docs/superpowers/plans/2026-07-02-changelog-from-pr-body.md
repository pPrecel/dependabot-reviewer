# Changelog from PR Body Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `get_changelog` MCP tool and instead extract changelog text directly from the PR body inside `get_pr_details`, returning it as `changelog_excerpt` in `PRDetails`.

**Architecture:** A new `body_parser.py` module handles extraction from both dependabot (HTML blockquote format) and ospo-renovate (Markdown `### Release Notes` format). The extracted text is added to `PRDetails` so the skill can read it without an extra tool call. `get_changelog`, `Changelog` model, `get_release`, and `get_file` are deleted.

**Tech Stack:** Python 3.12+, pytest, pydantic v2, html.parser (stdlib)

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Create | `mcp-server/dependabot_mcp/body_parser.py` | New — `extract_changelog(body: str) -> str` |
| Create | `mcp-server/tests/unit/test_body_parser.py` | New — unit tests for `extract_changelog` |
| Modify | `mcp-server/dependabot_mcp/models.py` | Add `changelog_excerpt: str` to `PRDetails`; remove `Changelog` model |
| Modify | `mcp-server/tests/unit/test_models.py` | Add `changelog_excerpt` to `test_pr_details_fields`; remove `test_changelog_not_found` |
| Modify | `mcp-server/dependabot_mcp/server.py` | Wire `extract_changelog` into `get_pr_details`; delete `get_changelog` tool |
| Modify | `mcp-server/dependabot_mcp/github_client.py` | Delete `get_release` and `get_file` methods |
| Modify | `skills/dependabot-review/SKILL.md` | Replace Step B3 (get_changelog call) with reading `changelog_excerpt` from PRDetails |

---

## Task 1: Create `body_parser.py` with tests (TDD)

**Files:**
- Create: `mcp-server/dependabot_mcp/body_parser.py`
- Create: `mcp-server/tests/unit/test_body_parser.py`

- [ ] **Step 1: Write failing tests**

Create `mcp-server/tests/unit/test_body_parser.py`:

```python
from dependabot_mcp.body_parser import extract_changelog

# ── dependabot HTML format ────────────────────────────────────────────────────

DEPENDABOT_RELEASE_NOTES = """Bumps [github.com/onsi/gomega](https://github.com/onsi/gomega) from 1.41.0 to 1.42.1.

Release notes
<p><em>Sourced from <a href="https://github.com/onsi/gomega/releases">github.com/onsi/gomega&#39;s releases</a>.</em></p>
<blockquote>
<h2>v1.42.1</h2>
<p>Bump Dependencies</p>
<h2>v1.42.0</h2>
<p>Add a set of Claude skills</p>
</blockquote>

Commits
<ul>
<li>See full diff in <a href="https://github.com/onsi/gomega/compare/v1.41.0...v1.42.1">compare view</a></li>
</ul>
"""

DEPENDABOT_CHANGELOG_SECTION = """Bumps foo from 1.0.0 to 1.1.0.

Release notes
<p><em>Sourced from foo's releases.</em></p>
<blockquote>
<h2>v1.1.0</h2>
<p>New features added</p>
</blockquote>

Changelog
<p><em>Sourced from <a href="https://github.com/foo/foo/blob/master/CHANGELOG.md">foo&#39;s changelog</a>.</em></p>
<blockquote>
<h2>1.1.0</h2>
<p>- feat: add new thing</p>
</blockquote>

Commits
<ul><li>See full diff</li></ul>
"""

DEPENDABOT_NO_CHANGELOG = """Bumps kyma-project/restricted-prod/sap.com/node-fips from 22.23.0-dev to 22.23.1-dev

Updates `kyma-project/restricted-prod/sap.com/node-fips` from 22.23.0-dev to 22.23.1-dev

Commits
<ul>
<li>See full diff in <a href="https://github.com/chainguard-images/images-private/commits">compare view</a></li>
</ul>
"""

# ── renovate Markdown format ──────────────────────────────────────────────────

RENOVATE_WITH_NOTES = """This PR contains the following updates:

| Package | Change |
|---|---|
| github.com/docker/cli | v29.5.3 → v29.6.1 |

---

### Release Notes

docker/cli (github.com/docker/cli)

### [`v29.6.1`](https://github.com/docker/cli/compare/v29.6.0...v29.6.1)

[Compare Source](https://github.com/docker/cli/compare/v29.6.0...v29.6.1)

### [`v29.6.0`](https://github.com/docker/cli/compare/v29.5.3...v29.6.0)

[Compare Source](https://github.com/docker/cli/compare/v29.5.3...v29.6.0)

---

### Configuration
"""

RENOVATE_COMPARE_ONLY = """This PR contains the following updates:

| Package | Change |
|---|---|
| k8s.io/utils | ff6756f → be93311 |

---

### Release Notes

<spoiler>

</spoiler>

---

### Configuration
"""

RENOVATE_NO_NOTES_SECTION = """This PR contains the following updates:

| Package | Type | Update | Change |
|---|---|---|---|
| k8s.io/utils | require | digest | ff6756f → be93311 |

---

### Configuration
"""


def test_dependabot_release_notes_html():
    result = extract_changelog(DEPENDABOT_RELEASE_NOTES)
    assert "v1.42.1" in result
    assert "Bump Dependencies" in result
    assert "v1.42.0" in result
    assert "<" not in result  # no raw HTML tags


def test_dependabot_prefers_release_notes_over_changelog():
    result = extract_changelog(DEPENDABOT_CHANGELOG_SECTION)
    assert "v1.1.0" in result
    assert "New features added" in result


def test_dependabot_no_changelog_returns_empty():
    result = extract_changelog(DEPENDABOT_NO_CHANGELOG)
    assert result == ""


def test_renovate_with_real_notes():
    result = extract_changelog(RENOVATE_WITH_NOTES)
    assert "v29.6.1" in result
    assert "v29.6.0" in result


def test_renovate_compare_links_only_returns_empty():
    result = extract_changelog(RENOVATE_COMPARE_ONLY)
    assert result == ""


def test_renovate_no_release_notes_section_returns_empty():
    result = extract_changelog(RENOVATE_NO_NOTES_SECTION)
    assert result == ""


def test_empty_body_returns_empty():
    assert extract_changelog("") == ""


def test_none_body_returns_empty():
    # body_parser must handle None gracefully (callers may pass pr["body"] which can be None)
    assert extract_changelog(None) == ""  # type: ignore[arg-type]


def test_truncates_at_2000_chars():
    long_notes = "x" * 3000
    body = f"### Release Notes\n\n{long_notes}\n\n---\n"
    result = extract_changelog(body)
    assert len(result) <= 2000
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd mcp-server
.venv/bin/python -m pytest tests/unit/test_body_parser.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'dependabot_mcp.body_parser'`

- [ ] **Step 3: Implement `body_parser.py`**

Create `mcp-server/dependabot_mcp/body_parser.py`:

```python
import re
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []

    def handle_data(self, data: str) -> None:
        self._text.append(data)

    def get_text(self) -> str:
        return "".join(self._text)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.get_text().strip()


def _is_compare_links_only(text: str) -> bool:
    """Return True if the only substantive content is Compare Source links."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    meaningful = [
        l for l in lines
        if l and not l.startswith("[Compare Source]") and not l.startswith("###")
    ]
    return len(meaningful) == 0


_MAX_LEN = 2000

# Renovate: content between "### Release Notes" and the next "---" separator
_RENOVATE_RE = re.compile(
    r"###\s+Release Notes\s*\n(.*?)(?:\n---|\Z)",
    re.DOTALL,
)

# Dependabot: <blockquote> immediately following "Release notes" heading
_DEPENDABOT_BLOCKQUOTE_RE = re.compile(
    r"Release notes\s*\n.*?<blockquote>(.*?)</blockquote>",
    re.DOTALL | re.IGNORECASE,
)


def extract_changelog(body: str | None) -> str:
    if not body:
        return ""

    # 1. Try renovate Markdown "### Release Notes" section
    m = _RENOVATE_RE.search(body)
    if m:
        content = m.group(1).strip()
        if not _is_compare_links_only(content):
            return content[:_MAX_LEN]

    # 2. Try dependabot HTML blockquote under "Release notes" heading
    m = _DEPENDABOT_BLOCKQUOTE_RE.search(body)
    if m:
        text = _html_to_text(m.group(1))
        if text:
            return text[:_MAX_LEN]

    return ""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd mcp-server
.venv/bin/python -m pytest tests/unit/test_body_parser.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp-server/dependabot_mcp/body_parser.py mcp-server/tests/unit/test_body_parser.py
git commit -m "feat: add body_parser to extract changelog from PR body"
```

---

## Task 2: Add `changelog_excerpt` to `PRDetails`, remove `Changelog` model

**Files:**
- Modify: `mcp-server/dependabot_mcp/models.py`
- Modify: `mcp-server/tests/unit/test_models.py`

- [ ] **Step 1: Update failing test first**

In `mcp-server/tests/unit/test_models.py`:

1. Remove the import of `Changelog` from the import line:
   ```python
   # Before:
   from dependabot_mcp.models import (
       PRSummary, Review, DiffClassification,
       PRDetails, Changelog, PrepareMergeResult, CommentResult,
   )
   # After:
   from dependabot_mcp.models import (
       PRSummary, Review, DiffClassification,
       PRDetails, PrepareMergeResult, CommentResult,
   )
   ```

2. Update `test_pr_details_fields` to include `changelog_excerpt`:
   ```python
   def test_pr_details_fields():
       details = PRDetails(
           reviews=[Review(author="bot", state="APPROVED")],
           auto_merge_set=True,
           ci_status="passing",
           failing_checks=[],
           merge_state="clean",
           diff_classification=DiffClassification(
               type="manifest", semver="patch",
               library="foo", old_version="1.0.0", new_version="1.0.1",
           ),
           comments=[],
           changelog_excerpt="v1.0.1\n- fix: something",
       )
       assert details.ci_status == "passing"
       assert details.auto_merge_set is True
       assert details.changelog_excerpt == "v1.0.1\n- fix: something"
   ```

3. Remove `test_changelog_not_found` entirely.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mcp-server
.venv/bin/python -m pytest tests/unit/test_models.py -v 2>&1 | head -20
```

Expected: `TypeError: PRDetails.__init__() got an unexpected keyword argument 'changelog_excerpt'`

- [ ] **Step 3: Update `models.py`**

In `mcp-server/dependabot_mcp/models.py`:

1. Add `changelog_excerpt` to `PRDetails`:
   ```python
   class PRDetails(BaseModel):
       reviews: list[Review]
       auto_merge_set: bool
       ci_status: Literal["passing", "failing", "pending"]
       failing_checks: list[CheckResult]
       merge_state: str
       diff_classification: DiffClassification
       comments: list[Comment]
       changelog_excerpt: str
   ```

2. Remove the entire `Changelog` class:
   ```python
   # DELETE this:
   class Changelog(BaseModel):
       found: bool
       excerpt: str
       source: Literal["github-release", "changelog-file", "not-found"]
   ```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd mcp-server
.venv/bin/python -m pytest tests/unit/test_models.py -v
```

Expected: all tests PASS (test_changelog_not_found is gone, rest pass).

- [ ] **Step 5: Commit**

```bash
git add mcp-server/dependabot_mcp/models.py mcp-server/tests/unit/test_models.py
git commit -m "feat: add changelog_excerpt to PRDetails, remove Changelog model"
```

---

## Task 3: Wire `extract_changelog` into `get_pr_details`, remove `get_changelog` tool

**Files:**
- Modify: `mcp-server/dependabot_mcp/server.py`

- [ ] **Step 1: Update `server.py`**

Open `mcp-server/dependabot_mcp/server.py` and make these changes:

1. Add import at the top (after existing imports):
   ```python
   from .body_parser import extract_changelog
   ```

2. Remove `Changelog` from the models import line:
   ```python
   # Before:
   from .models import (
       PRSummary, Review, CheckResult, DiffClassification,
       PRDetails, Comment, Changelog, PrepareMergeResult, CommentResult,
   )
   # After:
   from .models import (
       PRSummary, Review, CheckResult, DiffClassification,
       PRDetails, Comment, PrepareMergeResult, CommentResult,
   )
   ```

3. In `get_pr_details`, add `changelog_excerpt` to the `PRDetails(...)` constructor call. The current call ends at `comments=comments,`. Change it to:
   ```python
   return PRDetails(
       reviews=reviews,
       auto_merge_set=auto_merge_set,
       ci_status=ci_status,
       failing_checks=failing,
       merge_state=merge_state,
       diff_classification=diff_classification,
       comments=comments,
       changelog_excerpt=extract_changelog(pr.get("body") or ""),
   ).model_dump()
   ```

4. Delete the entire `get_changelog` tool function (lines starting with `@mcp.tool()` above `async def get_changelog(...)` through its `return` statement), and also delete the `_extract_changelog_section` helper function at the bottom of the file.

- [ ] **Step 2: Run full test suite**

```bash
cd mcp-server
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -15
```

Expected: all tests PASS. If any test imports `Changelog` from `server.py` or calls `get_changelog`, it will fail — fix by removing those references.

- [ ] **Step 3: Commit**

```bash
git add mcp-server/dependabot_mcp/server.py
git commit -m "feat: wire extract_changelog into get_pr_details, remove get_changelog tool"
```

---

## Task 4: Remove `get_release` and `get_file` from `github_client.py`

**Files:**
- Modify: `mcp-server/dependabot_mcp/github_client.py`

- [ ] **Step 1: Delete the two methods**

In `mcp-server/dependabot_mcp/github_client.py`, delete:

```python
# DELETE this entire method:
async def get_release(self, repo: str, tag: str) -> dict:
    r = await self._client.get(f"/repos/{repo}/releases/tags/{tag}")
    r.raise_for_status()
    return r.json()

# DELETE this entire method:
async def get_file(self, repo: str, path: str) -> str:
    r = await self._client.get(f"/repos/{repo}/contents/{path}")
    r.raise_for_status()
    data = r.json()
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"].replace("\n", "")).decode()
    return data.get("content", "")
```

Also delete the `import base64` at the top of the file if `base64` is no longer used elsewhere in the file.

- [ ] **Step 2: Run full test suite**

```bash
cd mcp-server
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add mcp-server/dependabot_mcp/github_client.py
git commit -m "chore: remove get_release and get_file from GithubClient"
```

---

## Task 5: Update `dependabot-review` skill

**Files:**
- Modify: `skills/dependabot-review/SKILL.md`

- [ ] **Step 1: Replace Step B3**

In `skills/dependabot-review/SKILL.md`, find and replace the Step B3 section:

**Find (current Step B3):**
```markdown
### Step B3: Fetch changelog (if needed)

Derive `library_repo` from the PR diff or title:
- For Go modules like `github.com/foo/bar` → `library_repo = "foo/bar"`
- For npm packages with a known GitHub repo → use the repo URL from package metadata
- For packages where the GitHub repo cannot be determined → skip changelog, treat as no breaking changes

```
get_changelog(host, token, library_repo=..., new_version=pr.diff_classification.new_version)
```
```

**Replace with:**
```markdown
### Step B3: Read changelog (from PR details)

The changelog is already available in `diff_classification.changelog_excerpt` from the `get_pr_details` result fetched in Step B1. No additional tool call is needed.

- If `changelog_excerpt` is non-empty → use it for breaking-change analysis in Step B4
- If `changelog_excerpt` is empty → treat as no changelog available; apply conservative defaults from decision table
```

- [ ] **Step 2: Verify the skill still references `changelog_excerpt` correctly in Step B4 decision table**

Read through the decision table in Step B4 to confirm it refers to "changelog" generically (not to `get_changelog` output). No changes needed to the table itself — it already says "Changelog mentions breaking changes" which applies equally to `changelog_excerpt`.

- [ ] **Step 3: Commit**

```bash
git add skills/dependabot-review/SKILL.md
git commit -m "docs: update dependabot-review skill to read changelog from PRDetails"
```

---

## Task 6: Final check and push

- [ ] **Step 1: Run full test suite one last time**

```bash
cd mcp-server
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests PASS, none skipped.

- [ ] **Step 2: Verify no remaining references to `get_changelog` or `Changelog`**

```bash
grep -r "get_changelog\|Changelog" /Users/I517616/go/src/github.com/pPrecel/dependabot-reviewer/mcp-server/dependabot_mcp/ \
  /Users/I517616/go/src/github.com/pPrecel/dependabot-reviewer/skills/
```

Expected: no output (zero matches).

- [ ] **Step 3: Push**

```bash
git push
```
