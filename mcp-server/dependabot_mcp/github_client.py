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
