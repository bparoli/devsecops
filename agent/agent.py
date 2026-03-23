import logging
from datetime import datetime, timedelta, timezone

import anthropic

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
    ):
        self.loki = LokiClient(loki_url)
        self.telegram = TelegramClient(telegram_token, telegram_chat_id)
        self.claude = anthropic.Anthropic(api_key=anthropic_api_key)
        self._last_alert: datetime | None = None

    def check_and_diagnose(self) -> None:
        """Query Loki for recent errors, diagnose with Claude, send to Telegram."""
        if self._in_cooldown():
            return

        # Query slightly more than the poll interval to avoid gaps between windows
        logs = self.loki.query_errors(since=POLL_INTERVAL + timedelta(seconds=5))
        if not logs:
            return

        logger.info("Error logs detected, requesting diagnosis", extra={"count": len(logs)})

        diagnosis = self._diagnose(logs)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        message = f"🚨 *Platform Failure Detected*\n\n{diagnosis}\n\n_Detected at {timestamp}_"

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

    def _in_cooldown(self) -> bool:
        if self._last_alert is None:
            return False
        return (datetime.now(timezone.utc) - self._last_alert) < COOLDOWN
