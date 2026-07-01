from typing import Literal


def render_template(
    reason: Literal["failing-ci", "breaking-changes"],
    failing_checks: list[dict] | None,
    library: str,
    old_version: str,
    new_version: str,
    semver: str,
    changelog_excerpt: str | None,
) -> str:
    if reason == "failing-ci":
        rows = "\n".join(
            f"| {c['name']} | ❌ {c['state']} |"
            for c in (failing_checks or [])
        )
        return (
            "Dependabot PR requires manual action ⚠️\n\n"
            "**Reason**: CI checks are failing\n\n"
            "**Failing checks**:\n"
            "| Check | Status |\n"
            "|-------|--------|\n"
            f"{rows}\n\n"
            "**Next steps**: Fix the failing tests or configuration before this PR can be merged."
        )

    if reason == "breaking-changes":
        excerpt_block = f"> {changelog_excerpt}" if changelog_excerpt else "> (no excerpt available)"
        return (
            "Dependabot PR requires manual action ⚠️\n\n"
            "**Reason**: Breaking changes detected in changelog\n\n"
            f"**{library}**: v{old_version} → v{new_version} ({semver})\n\n"
            "**Relevant changelog excerpt**:\n"
            f"{excerpt_block}\n\n"
            "**Next steps**: Review the breaking changes above and update the codebase accordingly."
        )

    raise ValueError(f"Unknown reason: {reason!r}")
