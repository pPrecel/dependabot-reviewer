import asyncio
from mcp.server.fastmcp import FastMCP
from .github_client import GithubClient
from .classifier import classify_diff
from .models import (
    PRSummary, Review, CheckResult, DiffClassification,
    PRDetails, Comment, Changelog, PrepareMergeResult, CommentResult,
)

mcp = FastMCP("dependabot-reviewer")


def _is_github_com(host: str) -> bool:
    return host == "github.com"


def _dependabot_author(host: str) -> str:
    # On github.com Dependabot is a GitHub App; on GHES it's a regular user
    return "app/dependabot" if _is_github_com(host) else "dependabot"


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
    author = _dependabot_author(host)
    q1 = f"is:open is:pr author:{author} review-requested:@me"
    q2 = f"is:open is:pr author:{author} reviewed-by:@me"
    r1, r2 = await asyncio.gather(
        client.search_prs(q1),
        client.search_prs(q2),
    )
    merged = []
    for item in r1 + r2:
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
    ).model_dump()
