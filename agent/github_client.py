import base64

import httpx


class GitHubClient:
    def __init__(self, token: str, repo: str):
        # repo = "owner/repo"
        self.repo = repo
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.client = httpx.Client(timeout=15)
        self._base = "https://api.github.com"

    def get_file(self, path: str) -> tuple[str, str]:
        """Return (content, sha) for the file at path."""
        resp = self.client.get(
            f"{self._base}/repos/{self.repo}/contents/{path}",
            headers=self.headers,
        )
        resp.raise_for_status()
        data = resp.json()
        content = base64.b64decode(data["content"]).decode()
        return content, data["sha"]

    def update_file(self, path: str, content: str, sha: str, message: str) -> str:
        """Commit updated content to path. Returns the new commit SHA."""
        encoded = base64.b64encode(content.encode()).decode()
        resp = self.client.put(
            f"{self._base}/repos/{self.repo}/contents/{path}",
            headers=self.headers,
            json={"message": message, "content": encoded, "sha": sha},
        )
        resp.raise_for_status()
        return resp.json()["commit"]["sha"]
