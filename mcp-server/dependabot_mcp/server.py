import asyncio
from mcp.server.fastmcp import FastMCP
from .github_client import GithubClient
from .classifier import classify_diff
from .body_parser import extract_changelog
from .models import (
    PRSummary, Review, CheckResult, DiffClassification,
    PRDetails, Comment, PrepareMergeResult, CommentResult,
    CheckLog, CommitResult,
)

mcp = FastMCP("dependabot-reviewer")


_BOT_AUTHORS = ["app/dependabot", "app/ospo-renovate"]


def _deduplicate(items: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    result = []
    for item in items:
        key = (item.get("repo", ""), item.get("number", 0))
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _repo_from_url(url: str) -> str:
    """Extract 'owner/repo' from a GitHub API repository_url."""
    # url like "https://api.github.com/repos/owner/repo"
    parts = url.rstrip("/").split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return url


@mcp.tool()
async def list_dependabot_prs(host: str, token: str) -> list[dict]:
    """
    List all open Dependabot PRs where the authenticated user (identified by token)
    is a requested reviewer or has already reviewed.
    Returns: list of {number, repo, title, url}
    """
    client = GithubClient(host, token)
    queries = [
        f"is:open is:pr author:{author} review-requested:@me"
        for author in _BOT_AUTHORS
    ] + [
        f"is:open is:pr author:{author} reviewed-by:@me"
        for author in _BOT_AUTHORS
    ]
    results = await asyncio.gather(*[client.search_prs(q) for q in queries], return_exceptions=True)
    merged = []
    for items in results:
        if isinstance(items, Exception):
            continue
        for item in items:
            repo = _repo_from_url(item.get("repository_url", ""))
            merged.append({
                "number": item["number"],
                "repo": repo,
                "title": item["title"],
                "url": item["html_url"],
            })
    return _deduplicate(merged)


@mcp.tool()
async def get_pr_details(host: str, token: str, repo: str, pr_number: int) -> dict:
    """
    Fetch all data needed to decide how to handle a PR:
    reviews, automerge status, CI status, merge state, diff classification, comments.
    Makes 4 parallel API calls for speed.
    """
    client = GithubClient(host, token)

    pr, reviews_raw, comments_raw, diff = await asyncio.gather(
        client.get_pr(repo, pr_number),
        client.get_pr_reviews(repo, pr_number),
        client.get_pr_comments(repo, pr_number),
        client.get_pr_diff(repo, pr_number),
    )

    # get check-runs needs the sha from pr — must be sequential
    sha = pr["head"]["sha"]
    checks_r = await client._client.get(
        f"/repos/{repo}/commits/{sha}/check-runs",
        params={"per_page": 100},
    )
    checks_r.raise_for_status()
    checks_raw = checks_r.json().get("check_runs", [])

    reviews = [Review(author=r["user"]["login"], state=r["state"]) for r in reviews_raw]

    auto_merge_set = pr.get("auto_merge") is not None

    failing = [
        CheckResult(name=c["name"], state=c["conclusion"] or c["status"])
        for c in checks_raw
        if c.get("conclusion") in ("failure", "error")
           or c.get("status") in ("failure", "error")
    ]
    if failing:
        ci_status = "failing"
    elif any(c.get("status") == "in_progress" or c.get("conclusion") is None for c in checks_raw):
        ci_status = "pending"
    else:
        ci_status = "passing"

    merge_state = pr.get("mergeable_state", "unknown")
    title = pr.get("title", "")
    diff_classification = classify_diff(diff, title)

    comments = [
        Comment(
            author=c["user"]["login"],
            body=c["body"],
            created_at=c["created_at"],
        )
        for c in comments_raw
    ]

    return PRDetails(
        reviews=reviews,
        auto_merge_set=auto_merge_set,
        ci_status=ci_status,
        failing_checks=failing,
        merge_state=merge_state,
        diff_classification=diff_classification,
        comments=comments,
        changelog_excerpt=extract_changelog(pr.get("body") or ""),
    ).model_dump()


@mcp.tool()
async def prepare_merge(host: str, token: str, repo: str, pr_number: int, comment: str) -> dict:
    """
    Orchestrate everything needed to bring a PR to a merged state.
    Steps: rebase/update → env deployments → automerge → approve.
    Returns status "done" or "needs_manual_rebase".
    Idempotent: skips automerge and approve if already set.
    """
    client = GithubClient(host, token)
    errors: list[str] = []
    branch_updated = False
    envs_approved = 0
    automerge_set = False
    approved = False

    # ── Step 1: rebase / update ──────────────────────────────────────────
    pr = await client.get_pr(repo, pr_number)
    merge_state = pr.get("mergeable_state", "unknown")

    if merge_state == "dirty":
        return PrepareMergeResult(
            status="needs_manual_rebase",
            automerge_set=False,
            approved=False,
            envs_approved=0,
            branch_updated=False,
            message="PR has merge conflicts that require manual resolution before merging.",
            errors=[],
        ).model_dump()

    if merge_state == "behind":
        try:
            await client.update_branch(repo, pr_number)
            branch_updated = True
            # Re-fetch PR to get the updated HEAD SHA after branch update,
            # then wait for GitHub to start new workflow runs before approving envs.
            await asyncio.sleep(10)
            pr = await client.get_pr(repo, pr_number)
        except Exception as e:
            errors.append(f"update_branch failed: {e}")

    # ── Step 2: env deployments ──────────────────────────────────────────
    sha = pr["head"]["sha"]
    checks_r = await client._client.get(
        f"/repos/{repo}/commits/{sha}/check-runs",
        params={"per_page": 100},
    )
    checks_r.raise_for_status()
    checks = checks_r.json().get("check_runs", [])

    def _workflow_run_id(check: dict) -> int | None:
        """Extract workflow run ID from check-run details_url.

        details_url format: .../actions/runs/{workflow_run_id}/job/{check_run_id}
        The pending_deployments endpoint requires the workflow run ID, not the
        check-run ID — using the check-run ID causes 404s.
        """
        url = check.get("details_url", "")
        parts = url.split("/")
        try:
            idx = parts.index("runs")
            return int(parts[idx + 1])
        except (ValueError, IndexError):
            return None

    waiting_run_ids = [
        wid for c in checks
        if c.get("status") == "waiting" or c.get("conclusion") == "waiting"
        if (wid := _workflow_run_id(c)) is not None
    ]
    for run_id in waiting_run_ids:
        try:
            deployments = await client.get_pending_deployments(repo, run_id)
            approvable = [d["environment"]["id"] for d in deployments if d.get("current_user_can_approve")]
            if approvable:
                await client.approve_deployment(repo, run_id, approvable)
                envs_approved += len(approvable)
        except Exception as e:
            errors.append(f"env approval for run {run_id} failed: {e}")

    # ── Step 3: automerge ────────────────────────────────────────────────
    if pr.get("auto_merge") is None:
        try:
            await client.enable_automerge(repo, pr_number)
            automerge_set = True
        except Exception as e:
            errors.append(f"enable_automerge failed: {e}")
    # else: already set — skip

    # ── Step 4: approve ──────────────────────────────────────────────────
    reviews = await client.get_pr_reviews(repo, pr_number)
    # Determine current user login from token
    me_r = await client._client.get("/user")
    me_login = me_r.json().get("login", "") if me_r.status_code == 200 else ""

    already_approved = any(
        r.get("state") == "APPROVED" and r.get("user", {}).get("login") == me_login
        for r in reviews
    )
    if not already_approved:
        try:
            await client.post_review(repo, pr_number, comment)
            approved = True
        except Exception as e:
            errors.append(f"post_review failed: {e}")

    return PrepareMergeResult(
        status="done",
        automerge_set=automerge_set,
        approved=approved,
        envs_approved=envs_approved,
        branch_updated=branch_updated,
        message="",
        errors=errors,
    ).model_dump()


@mcp.tool()
async def post_action_required_comment(
    host: str,
    token: str,
    repo: str,
    pr_number: int,
    reason: str,           # "failing-ci" | "breaking-changes"
    library: str,
    old_version: str,
    new_version: str,
    semver: str,
    failing_checks: list[dict] | None = None,
    changelog_excerpt: str | None = None,
) -> dict:
    """
    Post a structured ACTION REQUIRED comment on a PR using a fixed template.
    reason: "failing-ci" or "breaking-changes"
    """
    from .templates import render_template
    body = render_template(
        reason=reason,
        failing_checks=failing_checks,
        library=library,
        old_version=old_version,
        new_version=new_version,
        semver=semver,
        changelog_excerpt=changelog_excerpt,
    )
    client = GithubClient(host, token)
    result = await client.post_comment(repo, pr_number, body)
    return CommentResult(comment_url=result["html_url"]).model_dump()


@mcp.tool()
async def get_check_logs(host: str, token: str, repo: str, check_run_id: int) -> dict:
    """
    Fetch full logs for a failing CI check run.
    Maps check_run_id → job_id via check-run details_url, then downloads logs.
    Writes logs to /tmp/dependabot-fix-logs/ and returns {job_id, name, file_path}.
    """
    client = GithubClient(host, token)
    check_run = await client.get_check_run(repo, check_run_id)
    name = check_run.get("name", str(check_run_id))
    details_url = check_run.get("details_url", "")
    # Extract job_id from details_url: .../actions/runs/{run_id}/job/{job_id}
    # Fall back to check_run_id if pattern not found
    parts = details_url.rstrip("/").split("/")
    try:
        job_id = int(parts[-1])
    except (ValueError, IndexError):
        job_id = check_run_id

    file_path = await client.get_job_logs(repo, job_id)
    return CheckLog(job_id=job_id, name=name, file_path=file_path).model_dump()


@mcp.tool()
async def commit_files(
    host: str,
    token: str,
    repo: str,
    branch: str,
    files: list[dict],
    message: str,
    head_sha: str,
) -> dict:
    """
    Atomically commit one or more file changes to a branch via GraphQL createCommitOnBranch.
    files: list of {path: str, content: str} (raw text, server Base64-encodes it).
    head_sha: current HEAD SHA of the branch (expectedHeadOid for optimistic concurrency).
    Include [dependabot skip] in message to prevent Dependabot from force-pushing over the fix.
    Returns {commit_sha, commit_url}.
    """
    client = GithubClient(host, token)
    result = await client.commit_files_graphql(
        repo=repo,
        branch=branch,
        files=files,
        message=message,
        head_sha=head_sha,
    )
    return CommitResult(**result).model_dump()


@mcp.tool()
async def post_pr_comment(host: str, token: str, repo: str, pr_number: int, body: str) -> dict:
    """
    Post a plain-text comment on a PR/issue.
    Returns {comment_url}.
    """
    client = GithubClient(host, token)
    result = await client.post_comment(repo, pr_number, body)
    return CommentResult(comment_url=result["html_url"]).model_dump()


@mcp.tool()
async def get_raw_diff(host: str, token: str, repo: str, pr_number: int) -> str:
    """
    Fetch the raw unified diff of a pull request.
    Returns the diff as plain text. Use to find conflict markers (<<<<<<<).
    """
    client = GithubClient(host, token)
    return await client.get_pr_diff(repo, pr_number)


@mcp.tool()
async def get_file_contents(host: str, token: str, repo: str, path: str, ref: str | None = None) -> dict:
    """
    Fetch a file's content and blob SHA from a repository.
    ref: branch name, tag, or commit SHA (optional, defaults to default branch).
    Returns {content: str, sha: str} where content is decoded plain text.
    """
    client = GithubClient(host, token)
    return await client.get_file_contents(repo, path, ref=ref)


@mcp.tool()
async def get_pr_head_sha(host: str, token: str, repo: str, pr_number: int) -> str:
    """
    Get the current HEAD SHA of a pull request branch.
    Returns the SHA string. Re-fetch this after each commit_files call.
    """
    client = GithubClient(host, token)
    pr = await client.get_pr(repo, pr_number)
    return pr["head"]["sha"]


@mcp.tool()
async def get_check_run_ids(host: str, token: str, repo: str, head_sha: str) -> list[dict]:
    """
    List all check runs for a commit SHA.
    Returns list of {id, name, conclusion, status} for use with get_check_logs.
    """
    client = GithubClient(host, token)
    checks = await client.list_check_runs(repo, head_sha)
    return [
        {"id": c["id"], "name": c["name"], "conclusion": c.get("conclusion"), "status": c.get("status")}
        for c in checks
    ]
