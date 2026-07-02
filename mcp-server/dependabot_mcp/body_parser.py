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
    """Return True if the only substantive content is Compare Source links or HTML tags."""
    # Strip HTML tags to get plain text, then check for meaningful content
    plain = _html_to_text(text)
    lines = [l.strip() for l in plain.splitlines() if l.strip()]
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
