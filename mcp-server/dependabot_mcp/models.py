from typing import Literal
from pydantic import BaseModel


class PRSummary(BaseModel):
    number: int
    repo: str       # "owner/repo"
    title: str
    url: str


class Review(BaseModel):
    author: str
    state: str      # "APPROVED" | "CHANGES_REQUESTED" | "COMMENTED" | ...


class CheckResult(BaseModel):
    id: int
    name: str
    state: str      # "SUCCESS" | "FAILURE" | "ERROR" | "PENDING" | "WAITING"


class DiffClassification(BaseModel):
    type: Literal["lock-only", "manifest"]
    semver: Literal["patch", "minor", "major"] | None
    library: str
    old_version: str
    new_version: str


class Comment(BaseModel):
    author: str
    body: str
    created_at: str


class PRDetails(BaseModel):
    reviews: list[Review]
    auto_merge_set: bool
    ci_status: Literal["passing", "failing", "pending"]
    failing_checks: list[CheckResult]
    merge_state: str
    diff_classification: DiffClassification
    comments: list[Comment]
    changelog_excerpt: str


class PrepareMergeResult(BaseModel):
    status: Literal["done", "needs_manual_rebase"]
    automerge_set: bool
    approved: bool
    envs_approved: int
    branch_updated: bool
    message: str
    errors: list[str]


class CommentResult(BaseModel):
    comment_url: str


class CheckLog(BaseModel):
    job_id: int     # GitHub Actions numeric job ID
    name: str
    file_path: str


class CommitResult(BaseModel):
    commit_sha: str
    commit_url: str


class BranchCiStatus(BaseModel):
    sha: str
    branch: str
    ci_status: Literal["passing", "failing", "pending", "unknown"]
    failing_checks: list[dict]   # [{name: str, conclusion: str}]
    total_checks: int
    passing_checks: int
