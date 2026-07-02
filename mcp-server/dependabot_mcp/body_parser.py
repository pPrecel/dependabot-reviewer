import re
import html as _html_module
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []

    def handle_data(self, data: str) -> None:
        self._text.append(data)

    def get_text(self) -> str:
        return "".join(self._text)


def _html_to_text(html_str: str) -> str:
    parser = _TextExtractor()
    parser.feed(html_str)
    return _html_module.unescape(parser.get_text()).strip()


# Matches Renovate package-source attribution lines, e.g. "docker/cli (github.com/docker/cli)"
_RENOVATE_ATTRIBUTION_RE = re.compile(r"^[\w./\-]+ \([\w./\-]+\)$")


def _is_compare_links_only(text: str) -> bool:
    """Return True if the only substantive content is Compare Source links or HTML tags."""
    # Strip HTML tags to get plain text, then check for meaningful content
    plain = _html_to_text(text)
    lines = [line.strip() for line in plain.splitlines() if line.strip()]
    meaningful = [
        line for line in lines
        if not line.startswith("[Compare Source]")
        and not (line.startswith("### [") or line.startswith("### [`"))
        and not _RENOVATE_ATTRIBUTION_RE.match(line)
    ]
    return len(meaningful) == 0


_MAX_LEN = 2000

# Renovate: content between "### Release Notes" and the next "---" separator
_RENOVATE_RE = re.compile(
    r"^###\s+Release Notes\s*$\n(.*?)(?:\n---|\Z)",
    re.DOTALL | re.MULTILINE,
)

# Dependabot: <blockquote> immediately following "Release notes" heading.
# The outer blockquote regex uses a greedy inner match; we post-process the
# captured content to strip any nested blockquote tags.
_DEPENDABOT_BLOCKQUOTE_RE = re.compile(
    r"Release notes\s*\n.*?<blockquote>(.*)</blockquote>",
    re.DOTALL | re.IGNORECASE,
)

# Matches innermost nested <blockquote>…</blockquote> pairs for stripping.
_NESTED_BLOCKQUOTE_RE = re.compile(
    r"<blockquote>[^<]*(?:<(?!/?blockquote)[^<]*)*</blockquote>",
    re.DOTALL | re.IGNORECASE,
)


def _strip_nested_blockquotes(html_str: str) -> str:
    """Iteratively remove nested <blockquote>…</blockquote> pairs until none remain."""
    prev = None
    result = html_str
    while prev != result:
        prev = result
        result = _NESTED_BLOCKQUOTE_RE.sub("", result)
    return result


def extract_changelog(body: str | None) -> str:
    if not body:
        return ""

    # 1. Try renovate Markdown "### Release Notes" section
    m = _RENOVATE_RE.search(body)
    if m:
        content = m.group(1).strip()
        if not _is_compare_links_only(content):
            return content[:_MAX_LEN]

    # 2. Try dependabot HTML blockquote under "Release notes" heading.
    # Use a greedy match to capture up to the LAST </blockquote>, then strip
    # any nested blockquote tags from the captured content.
    m = _DEPENDABOT_BLOCKQUOTE_RE.search(body)
    if m:
        inner = _strip_nested_blockquotes(m.group(1))
        text = _html_to_text(inner)
        if text:
            return text[:_MAX_LEN]

    return ""
