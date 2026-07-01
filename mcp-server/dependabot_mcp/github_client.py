import base64
import httpx


class GithubClient:
    def __init__(self, host: str, token: str) -> None:
        if host == "github.com":
            base_url = "https://api.github.com/"
        else:
            base_url = f"https://{host}/api/v3/"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    # ── Read ──────────────────────────────────────────────────────────────

    async def search_prs(self, query: str) -> list[dict]:
        r = await self._client.get("/search/issues", params={"q": query, "per_page": 100})
        r.raise_for_status()
        return r.json()["items"]

    async def get_pr(self, repo: str, number: int) -> dict:
        r = await self._client.get(f"/repos/{repo}/pulls/{number}")
        r.raise_for_status()
        return r.json()

    async def get_pr_reviews(self, repo: str, number: int) -> list[dict]:
        r = await self._client.get(f"/repos/{repo}/pulls/{number}/reviews")
        r.raise_for_status()
        return r.json()

    async def get_pr_comments(self, repo: str, number: int) -> list[dict]:
        r = await self._client.get(f"/repos/{repo}/issues/{number}/comments")
        r.raise_for_status()
        return r.json()

    async def get_pr_checks(self, repo: str, number: int) -> list[dict]:
        # First get the PR to find head sha
        pr = await self.get_pr(repo, number)
        sha = pr["head"]["sha"]
        r = await self._client.get(
            f"/repos/{repo}/commits/{sha}/check-runs",
            params={"per_page": 100},
        )
        r.raise_for_status()
        return r.json().get("check_runs", [])

    async def get_pr_diff(self, repo: str, number: int) -> str:
        r = await self._client.get(
            f"/repos/{repo}/pulls/{number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        r.raise_for_status()
        return r.text

    async def get_release(self, repo: str, tag: str) -> dict:
        r = await self._client.get(f"/repos/{repo}/releases/tags/{tag}")
        r.raise_for_status()
        return r.json()

    async def get_file(self, repo: str, path: str) -> str:
        r = await self._client.get(f"/repos/{repo}/contents/{path}")
        r.raise_for_status()
        data = r.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"].replace("\n", "")).decode()
        return data.get("content", "")

    async def get_pending_deployments(self, repo: str, run_id: int) -> list[dict]:
        r = await self._client.get(f"/repos/{repo}/actions/runs/{run_id}/pending_deployments")
        r.raise_for_status()
        return r.json()

    # ── Write ─────────────────────────────────────────────────────────────

    async def post_review(self, repo: str, number: int, body: str) -> dict:
        r = await self._client.post(
            f"/repos/{repo}/pulls/{number}/reviews",
            json={"body": body, "event": "APPROVE"},
        )
        r.raise_for_status()
        return r.json()

    async def post_comment(self, repo: str, number: int, body: str) -> dict:
        r = await self._client.post(
            f"/repos/{repo}/issues/{number}/comments",
            json={"body": body},
        )
        r.raise_for_status()
        return r.json()

    async def enable_automerge(self, repo: str, number: int) -> dict:
        # GitHub GraphQL: enablePullRequestAutoMerge
        # First get the PR node_id
        pr = await self.get_pr(repo, number)
        node_id = pr["node_id"]
        query = """
        mutation($pullRequestId: ID!, $mergeMethod: PullRequestMergeMethod!) {
          enablePullRequestAutoMerge(input: {
            pullRequestId: $pullRequestId,
            mergeMethod: $mergeMethod
          }) {
            pullRequest { autoMergeRequest { mergeMethod } }
          }
        }
        """
        # Derive GraphQL endpoint from REST base_url
        base = str(self._client.base_url)
        if "api.github.com" in base:
            graphql_url = "https://api.github.com/graphql"
        else:
            host = base.split("/")[2]
            graphql_url = f"https://{host}/api/graphql"

        r = await self._client.post(
            graphql_url,
            json={"query": query, "variables": {"pullRequestId": node_id, "mergeMethod": "SQUASH"}},
        )
        r.raise_for_status()
        return r.json()

    async def update_branch(self, repo: str, number: int) -> dict:
        r = await self._client.put(
            f"/repos/{repo}/pulls/{number}/update-branch",
            json={},
        )
        r.raise_for_status()
        return r.json()

    async def approve_deployment(self, repo: str, run_id: int, env_ids: list[int]) -> dict:
        r = await self._client.post(
            f"/repos/{repo}/actions/runs/{run_id}/pending_deployments",
            json={
                "environment_ids": env_ids,
                "state": "approved",
                "comment": "Approving environment for Dependabot PR",
            },
        )
        r.raise_for_status()
        return r.json()

    async def __aenter__(self) -> "GithubClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()
