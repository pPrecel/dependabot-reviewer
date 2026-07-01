import re
from .models import DiffClassification

# Files whose presence alone makes a diff "manifest"
_MANIFEST_FILES = {
    "go.mod", "package.json", "pyproject.toml",
    "requirements.txt", "Pipfile", "Cargo.toml",
}
# Files that are lock-only
_LOCK_FILES = {
    "go.sum", "package-lock.json", "yarn.lock",
    "pnpm-lock.yaml", "Pipfile.lock", "poetry.lock",
    "uv.lock", "Cargo.lock",
}

# Dependabot title patterns: "bump X from OLD to NEW"
_TITLE_RE = re.compile(
    r"bump\s+(.+?)\s+from\s+([^\s]+)\s+to\s+([^\s]+)",
    re.IGNORECASE,
)


def _changed_files(diff: str) -> set[str]:
    files = set()
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            # "diff --git a/path/to/file b/path/to/file"
            parts = line.split(" ")
            if len(parts) >= 4:
                path = parts[3].lstrip("b/")
                files.add(path.split("/")[-1])  # basename
    return files


def _semver(old: str, new: str) -> str | None:
    def _parse(v: str) -> tuple[int, ...]:
        cleaned = v.lstrip("v~^>=<")
        parts = re.split(r"[.\-]", cleaned)
        nums = []
        for p in parts[:3]:
            try:
                nums.append(int(p))
            except ValueError:
                nums.append(0)
        while len(nums) < 3:
            nums.append(0)
        return tuple(nums)

    try:
        o = _parse(old)
        n = _parse(new)
        if n[0] != o[0]:
            return "major"
        if n[1] != o[1]:
            return "minor"
        return "patch"
    except Exception:
        return None


def classify_diff(diff: str, title: str) -> DiffClassification:
    changed = _changed_files(diff)
    is_manifest = bool(changed & _MANIFEST_FILES)

    m = _TITLE_RE.search(title)
    library = m.group(1).strip() if m else ""
    old_version = m.group(2).strip() if m else ""
    new_version = m.group(3).strip() if m else ""

    diff_type = "manifest" if is_manifest else "lock-only"
    semver = _semver(old_version, new_version) if old_version and new_version else None

    return DiffClassification(
        type=diff_type,
        semver=semver,
        library=library,
        old_version=old_version,
        new_version=new_version,
    )
