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

    def find_open_issues_for_remediation(self) -> list[dict]:
        """Return open Incidents not yet picked up for remediation."""
        exclude = ["in-remediation", "remediated", "remediation-rejected",
                   "remediation-not-applicable", "approval-timeout", "remediation-failed"]
        exclude_jql = ", ".join(f'"{l}"' for l in exclude)
        jql = (
            f'project = "{self.project_key}" AND issuetype = Incident '
            f'AND statusCategory != Done '
            f'AND (labels is EMPTY OR labels not in ({exclude_jql})) '
            f'ORDER BY created ASC'
        )
        resp = self.client.get(
            f"{self.base_url}/rest/api/3/search/jql",
            headers=self.headers,
            params={"jql": jql, "maxResults": 5, "fields": "summary,status,labels,description"},
        )
        resp.raise_for_status()
        return resp.json().get("issues", [])

    def add_label(self, issue_key: str, label: str) -> None:
        """Append a label to an issue without removing existing ones."""
        resp = self.client.get(
            f"{self.base_url}/rest/api/3/issue/{issue_key}",
            headers=self.headers,
            params={"fields": "labels"},
        )
        resp.raise_for_status()
        current = resp.json()["fields"].get("labels", [])
        if label in current:
            return
        self.client.put(
            f"{self.base_url}/rest/api/3/issue/{issue_key}",
            headers=self.headers,
            json={"fields": {"labels": current + [label]}},
        ).raise_for_status()

    def transition_to_done(self, issue_key: str) -> None:
        """Move the issue to Done status."""
        resp = self.client.get(
            f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions",
            headers=self.headers,
        )
        resp.raise_for_status()
        transitions = resp.json().get("transitions", [])
        done_id = next(
            (t["id"] for t in transitions
             if t.get("to", {}).get("statusCategory", {}).get("key") == "done"),
            None,
        )
        if not done_id:
            return
        self.client.post(
            f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions",
            headers=self.headers,
            json={"transition": {"id": done_id}},
        ).raise_for_status()

    def issue_url(self, issue_key: str) -> str:
        return f"{self.base_url}/browse/{issue_key}"
