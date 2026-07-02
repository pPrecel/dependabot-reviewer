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
# Also matches @-scoped packages, e.g. "@angular/core (github.com/angular/angular)"
_RENOVATE_ATTRIBUTION_RE = re.compile(r"^[@\w./\-]+ \([@\w./\-]+\)$")


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


def _extract_dependabot_blockquote(body: str) -> str:
    """Extract text from first <blockquote> after 'Release notes' heading."""
    # Find "Release notes" heading (case-insensitive)
    lower = body.lower()
    heading_pos = lower.find("release notes\n")
    if heading_pos == -1:
        return ""
    # Find first <blockquote> after the heading
    start = body.find("<blockquote>", heading_pos)
    if start == -1:
        return ""
    start += len("<blockquote>")
    # Find matching </blockquote> — first one after <blockquote>
    end = body.find("</blockquote>", start)
    if end == -1:
        return ""
    return body[start:end]


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
    inner = _extract_dependabot_blockquote(body)
    if inner:
        text = _html_to_text(inner)
        if text:
            return text[:_MAX_LEN]

    return ""
