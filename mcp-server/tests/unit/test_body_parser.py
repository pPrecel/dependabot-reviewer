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

RENOVATE_WITH_REAL_NOTES = """This PR contains the following updates:

| Package | Change |
|---|---|
| github.com/google/go-containerregistry | v0.21.6 → v0.21.7 |

---

### Release Notes

google/go-containerregistry (github.com/google/go-containerregistry)

### [`v0.21.7`](https://github.com/google/go-containerregistry/releases/tag/v0.21.7)

[Compare Source](https://github.com/google/go-containerregistry/compare/v0.21.6...v0.21.7)

#### What's Changed

- tarball: return error instead of panicking on missing rootfs.diff_ids
- gcrane: honor --platform flag in copy
- mutate: verify layer digests in Extract and Time

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


def test_dependabot_release_notes_excludes_changelog_section():
    result = extract_changelog(DEPENDABOT_CHANGELOG_SECTION)
    # Should contain release notes content
    assert "New features added" in result
    # Should NOT contain changelog section content (sibling blockquote)
    assert "feat: add new thing" not in result


def test_dependabot_no_changelog_returns_empty():
    result = extract_changelog(DEPENDABOT_NO_CHANGELOG)
    assert result == ""


def test_renovate_with_only_compare_links_returns_empty():
    result = extract_changelog(RENOVATE_WITH_NOTES)
    assert result == ""


def test_renovate_with_real_notes():
    result = extract_changelog(RENOVATE_WITH_REAL_NOTES)
    assert "What's Changed" in result


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


def test_truncates_at_2000_chars_dependabot():
    long_content = "x" * 3000
    body = f"Release notes\n<p>source</p>\n<blockquote><p>{long_content}</p></blockquote>\n"
    result = extract_changelog(body)
    assert len(result) <= 2000
