import json
import logging
from datetime import datetime, timedelta, timezone

import anthropic

from jira import JiraClient
from loki import LokiClient
from telegram import TelegramClient

logger = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=30)
COOLDOWN = timedelta(minutes=2)

DIAGNOSIS_PROMPT = """\
You are a platform reliability engineer analyzing error logs from a Go arithmetic REST API running on Kubernetes.

Analyze these error logs and provide a concise diagnosis:

LOGS:
{logs}

Respond with:
1. *Root Cause*: What triggered the failure
2. *What Happened*: Brief description of the incident
3. *Fix*: Recommended action to resolve it

Keep the response under 250 words. Use plain text, no markdown headers.\
"""


class DiagnosticAgent:
    def __init__(
        self,
        loki_url: str,
        telegram_token: str,
        telegram_chat_id: str,
        anthropic_api_key: str,
        jira_url: str | None = None,
        jira_email: str | None = None,
        jira_api_token: str | None = None,
        jira_project_key: str | None = None,
    ):
        self.loki = LokiClient(loki_url)
        self.telegram = TelegramClient(telegram_token, telegram_chat_id)
        self.claude = anthropic.Anthropic(api_key=anthropic_api_key)
        self._last_alert: datetime | None = None

        self.jira: JiraClient | None = None
        if all([jira_url, jira_email, jira_api_token, jira_project_key]):
            self.jira = JiraClient(jira_url, jira_email, jira_api_token, jira_project_key)
            logger.info("Jira integration enabled", extra={"project": jira_project_key})
        else:
            logger.info("Jira integration disabled (missing config)")

    def check_and_diagnose(self) -> None:
        """Query Loki for recent errors, diagnose with Claude, notify via Telegram and Jira."""
        if self._in_cooldown():
            return

        logs = self.loki.query_errors(since=POLL_INTERVAL + timedelta(seconds=5))
        if not logs:
            return

        logger.info("Error logs detected, requesting diagnosis", extra={"count": len(logs)})

        diagnosis = self._diagnose(logs)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        jira_note = self._handle_jira(logs, diagnosis)

        message = (
            f"🚨 *Platform Failure Detected*\n\n"
            f"{diagnosis}\n\n"
            f"{jira_note}"
            f"_Detected at {timestamp}_"
        )

        self.telegram.send(message)
        self._last_alert = datetime.now(timezone.utc)
        logger.info("Diagnosis sent to Telegram")

    def _diagnose(self, logs: list[str]) -> str:
        prompt = DIAGNOSIS_PROMPT.format(logs="\n".join(logs))

        with self.claude.messages.stream(
            model="claude-opus-4-6",
            max_tokens=1024,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            return stream.get_final_message().content[-1].text

    def _handle_jira(self, logs: list[str], diagnosis: str) -> str:
        """Check for an open Jira issue; create one if none exists. Returns a note for Telegram."""
        if self.jira is None:
            return ""

        try:
            summary = self._issue_summary(logs)
            existing = self.jira.find_open_issue(summary)
            if existing:
                key = existing["key"]
                status = existing["fields"]["status"]["name"]
                url = self.jira.issue_url(key)
                logger.info("Open Jira issue found, skipping creation", extra={"key": key})
                return f"📋 Open issue: [{key}]({url}) \\({status}\\)\n\n"

            created = self.jira.create_issue(summary=summary, description=diagnosis)
            key = created["key"]
            url = self.jira.issue_url(key)
            logger.info("Jira issue created", extra={"key": key})
            return f"📋 Jira issue created: [{key}]({url})\n\n"

        except Exception as exc:
            logger.error(f"Jira integration failed: {exc}")
            return ""

    def _issue_summary(self, logs: list[str]) -> str:
        """Extract a short error title from the raw log lines."""
        for line in logs:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                msg = data.get("msg") or data.get("message") or data.get("error", "")
                if msg:
                    return str(msg)[:120]
            except (json.JSONDecodeError, AttributeError):
                # Plain text: skip timestamp/level tokens and return the rest
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.upper() in ("ERROR", "WARN", "WARNING"):
                        rest = " ".join(parts[i + 1 :])
                        if rest:
                            return rest[:120]
                return line[:120]
        return "arithmetic-api failure detected"

    def _in_cooldown(self) -> bool:
        if self._last_alert is None:
            return False
        return (datetime.now(timezone.utc) - self._last_alert) < COOLDOWN
