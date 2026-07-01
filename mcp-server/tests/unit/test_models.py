import pytest
from dependabot_mcp.models import (
    PRSummary, Review, CheckResult, DiffClassification,
    PRDetails, Changelog, PrepareMergeResult, CommentResult,
)


def test_pr_summary_fields():
    pr = PRSummary(number=1, repo="owner/repo", title="bump foo", url="https://github.com/owner/repo/pull/1")
    assert pr.number == 1
    assert pr.repo == "owner/repo"


def test_diff_classification_semver_optional():
    dc = DiffClassification(type="lock-only", semver=None, library="foo", old_version="1.0.0", new_version="1.0.1")
    assert dc.semver is None


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
    )
    assert details.ci_status == "passing"
    assert details.auto_merge_set is True


def test_prepare_merge_result_defaults():
    result = PrepareMergeResult(
        status="done",
        automerge_set=True,
        approved=True,
        envs_approved=2,
        branch_updated=False,
        message="",
        errors=[],
    )
    assert result.status == "done"
    assert result.envs_approved == 2


def test_changelog_not_found():
    c = Changelog(found=False, excerpt="", source="not-found")
    assert c.found is False


def test_comment_result():
    r = CommentResult(comment_url="https://github.com/owner/repo/issues/1#issuecomment-123")
    assert "issuecomment" in r.comment_url
