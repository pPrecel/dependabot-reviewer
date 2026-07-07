import base64
import os
import re

import httpx


_client_cache: dict[tuple[str, str], "GithubClient"] = {}


def get_client(host: str, token: str) -> "GithubClient":
    key = (host, token)
    if key not in _client_cache:
        _client_cache[key] = GithubClient(host, token)
    return _client_cache[key]


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
        r = await self._client.get(f"/repos/{repo}/issues/{number}/comments", params={"per_page": 100})
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

    async def get_pending_deployments(self, repo: str, run_id: int) -> list[dict]:
        r = await self._client.get(f"/repos/{repo}/actions/runs/{run_id}/pending_deployments")
        r.raise_for_status()
        return r.json()

    async def get_job_logs(self, repo: str, job_id: int) -> str:
        """Fetch CI job logs and write to /tmp file. Returns file path."""
        log_dir = os.environ.get("DEPENDABOT_FIX_LOG_DIR", "/tmp/dependabot-fix-logs")
        os.makedirs(log_dir, exist_ok=True)
        repo_escaped = re.sub(r"[^a-zA-Z0-9_-]", "-", repo)
        file_path = os.path.join(log_dir, f"{repo_escaped}-{job_id}.txt")

        # Follow redirect manually — httpx does not follow cross-origin redirects by default
        r = await self._client.get(f"/repos/{repo}/actions/jobs/{job_id}/logs", follow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308):
            redirect_url = r.headers.get("location")
            if not redirect_url:
                raise ValueError(f"GitHub returned {r.status_code} without a location header for job logs")
            async with httpx.AsyncClient() as plain_client:
                r2 = await plain_client.get(redirect_url)
                r2.raise_for_status()
                log_text = r2.text
        else:
            r.raise_for_status()
            log_text = r.text

        with open(file_path, "w") as f:
            f.write(log_text)
        return file_path

    async def get_check_run(self, repo: str, check_run_id: int) -> dict:
        r = await self._client.get(f"/repos/{repo}/check-runs/{check_run_id}")
        r.raise_for_status()
        return r.json()

    async def get_file_contents(self, repo: str, path: str, ref: str | None = None) -> dict:
        """Fetch a file's content and blob SHA from GitHub. Returns {content: str, sha: str}."""
        params = {}
        if ref:
            params["ref"] = ref
        r = await self._client.get(f"/repos/{repo}/contents/{path}", params=params)
        r.raise_for_status()
        data = r.json()
        raw = base64.b64decode(data["content"].replace("\n", "")).decode("utf-8", errors="replace")
        return {"content": raw, "sha": data["sha"]}

    async def list_check_runs(self, repo: str, head_sha: str) -> list[dict]:
        r = await self._client.get(
            f"/repos/{repo}/commits/{head_sha}/check-runs",
            params={"per_page": 100},
        )
        r.raise_for_status()
        return r.json().get("check_runs", [])

    async def get_branch_head_sha(self, repo: str, branch: str) -> str:
        """Fetch HEAD commit SHA for a branch. Raises HTTPStatusError on 404."""
        r = await self._client.get(f"/repos/{repo}/git/ref/heads/{branch}")
        r.raise_for_status()
        return r.json()["object"]["sha"]

    # ── Write ─────────────────────────────────────────────────────────────

    async def create_pull_request(
        self,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: str,
    ) -> dict:
        r = await self._client.post(
            f"/repos/{repo}/pulls",
            json={"title": title, "head": head, "base": base, "body": body},
        )
        r.raise_for_status()
        data = r.json()
        return {"pr_number": data["number"], "pr_url": data["html_url"]}

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

    async def enable_automerge(self, node_id: str) -> dict:
        # GitHub GraphQL: enablePullRequestAutoMerge
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

    async def commit_files_graphql(
        self,
        repo: str,
        branch: str,
        files: list[dict],  # [{path: str, content: str}]
        message: str,
        head_sha: str,
    ) -> dict:
        """Atomically commit multiple files via GraphQL createCommitOnBranch."""
        additions = [
            {"path": f["path"], "contents": base64.b64encode(f["content"].encode()).decode()}
            for f in files
        ]
        query = """
        mutation($input: CreateCommitOnBranchInput!) {
          createCommitOnBranch(input: $input) {
            commit { oid url }
          }
        }
        """
        variables = {
            "input": {
                "branch": {"repositoryNameWithOwner": repo, "branchName": branch},
                "message": {"headline": message},
                "fileChanges": {"additions": additions},
                "expectedHeadOid": head_sha,
            }
        }
        base = str(self._client.base_url)
        if "api.github.com" in base:
            graphql_url = "https://api.github.com/graphql"
        else:
            host = base.split("/")[2]
            graphql_url = f"https://{host}/api/graphql"

        r = await self._client.post(graphql_url, json={"query": query, "variables": variables})
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise ValueError(f"GraphQL errors: {data['errors']}")
        commit = data["data"]["createCommitOnBranch"]["commit"]
        return {"commit_sha": commit["oid"], "commit_url": commit["url"]}

    async def __aenter__(self) -> "GithubClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()
