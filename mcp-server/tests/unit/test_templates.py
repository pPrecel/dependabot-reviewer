from dependabot_mcp.templates import render_template


def test_failing_ci_template():
    result = render_template(
        reason="failing-ci",
        failing_checks=[{"name": "unit-tests", "state": "FAILURE"}],
        library="github.com/foo/bar",
        old_version="1.0.0",
        new_version="1.0.1",
        semver="patch",
        changelog_excerpt=None,
    )
    assert "CI checks are failing" in result
    assert "unit-tests" in result
    assert "❌ FAILURE" in result
    assert "breaking" not in result


def test_breaking_changes_template():
    result = render_template(
        reason="breaking-changes",
        failing_checks=None,
        library="github.com/foo/bar",
        old_version="1.0.0",
        new_version="2.0.0",
        semver="major",
        changelog_excerpt="Removed `OldAPI`. Use `NewAPI` instead.",
    )
    assert "Breaking changes" in result
    assert "github.com/foo/bar" in result
    assert "v1.0.0" in result
    assert "v2.0.0" in result
    assert "Removed `OldAPI`" in result


def test_templates_are_deterministic():
    kwargs = dict(
        reason="failing-ci",
        failing_checks=[{"name": "lint", "state": "FAILURE"}],
        library="foo",
        old_version="1.0.0",
        new_version="1.0.1",
        semver="patch",
        changelog_excerpt=None,
    )
    assert render_template(**kwargs) == render_template(**kwargs)
