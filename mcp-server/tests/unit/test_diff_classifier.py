from dependabot_mcp.classifier import classify_diff
from dependabot_mcp.models import DiffClassification


def test_lock_only_go_sum():
    diff = "diff --git a/go.sum b/go.sum\n+some hash\n"
    result = classify_diff(diff, "gomod(deps): bump github.com/foo/bar from 1.0.0 to 1.0.1")
    assert result.type == "lock-only"


def test_manifest_gomod_patch():
    diff = "diff --git a/go.mod b/go.mod\n-github.com/foo/bar v1.0.0\n+github.com/foo/bar v1.0.1\ndiff --git a/go.sum b/go.sum\n+hash\n"
    result = classify_diff(diff, "gomod(deps): bump github.com/foo/bar from 1.0.0 to 1.0.1")
    assert result.type == "manifest"
    assert result.semver == "patch"
    assert result.library == "github.com/foo/bar"
    assert result.old_version == "1.0.0"
    assert result.new_version == "1.0.1"


def test_manifest_minor_bump():
    diff = "diff --git a/go.mod b/go.mod\n-v1.2.0\n+v1.3.0\n"
    result = classify_diff(diff, "gomod(deps): bump github.com/foo/bar from 1.2.0 to 1.3.0")
    assert result.semver == "minor"


def test_manifest_major_bump():
    diff = "diff --git a/go.mod b/go.mod\n-v1.0.0\n+v2.0.0\n"
    result = classify_diff(diff, "gomod(deps): bump github.com/foo/bar from 1.0.0 to 2.0.0")
    assert result.semver == "major"


def test_requirements_txt_manifest():
    diff = "diff --git a/requirements.txt b/requirements.txt\n-opentelemetry==1.42.0\n+opentelemetry==1.43.0\n"
    result = classify_diff(diff, "pip(deps): bump opentelemetry from 1.42.0 to 1.43.0")
    assert result.type == "manifest"
    assert result.semver == "minor"


def test_lockfile_only_yarn():
    diff = "diff --git a/yarn.lock b/yarn.lock\n+some entry\n"
    result = classify_diff(diff, "npm(deps): bump lodash from 4.17.20 to 4.17.21")
    assert result.type == "lock-only"


def test_title_parsing_bump_pattern():
    diff = "diff --git a/package.json b/package.json\n-\"lodash\": \"4.17.20\"\n+\"lodash\": \"4.17.21\"\n"
    result = classify_diff(diff, "build(deps): bump lodash from 4.17.20 to 4.17.21")
    assert result.library == "lodash"
    assert result.old_version == "4.17.20"
    assert result.new_version == "4.17.21"
