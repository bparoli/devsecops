import base64

import httpx


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str, project_key: str):
        self.base_url = base_url.rstrip("/")
        self.project_key = project_key
        credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.client = httpx.Client(timeout=10)

    def find_open_issue(self, summary: str) -> dict | None:
        """Return the most recent open issue matching the summary, or None."""
        safe = summary.replace('"', '\\"')
        jql = (
            f'project = "{self.project_key}" AND summary ~ "{safe}" '
            f'AND statusCategory != Done ORDER BY created DESC'
        )
        resp = self.client.get(
            #f"{self.base_url}/rest/api/3/issue/search",
            f"{self.base_url}/rest/api/3/search/jql",
            headers=self.headers,
            params={"jql": jql, "maxResults": 1, "fields": "summary,status"},
        )
        resp.raise_for_status()
        issues = resp.json().get("issues", [])
        return issues[0] if issues else None

    def create_issue(self, summary: str, description: str) -> dict:
        """Create a Bug issue and return the Jira response (contains key and self URL)."""
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}],
                        }
                    ],
                },
                "issuetype": {"name": "Incident"},
                "labels": ["arithmetic-api", "automated"],
            }
        }
        resp = self.client.post(
            f"{self.base_url}/rest/api/3/issue",
            headers=self.headers,
            json=payload,
        )
        if resp.is_error:
            raise httpx.HTTPStatusError(
                f"{resp.status_code} {resp.reason_phrase}: {resp.text}",
                request=resp.request,
                response=resp,
            )
        return resp.json()

    def issue_url(self, issue_key: str) -> str:
        return f"{self.base_url}/browse/{issue_key}"
