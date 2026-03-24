import logging
import os
import time

import anthropic

from github_client import GitHubClient
from jira import JiraClient
from remediation_agent import POLL_INTERVAL, RemediationAgent
from telegram import TelegramClient

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)


def must_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise SystemExit(f"Required environment variable not set: {key}")
    return value


def main() -> None:
    agent = RemediationAgent(
        jira=JiraClient(
            base_url=must_env("JIRA_URL"),
            email=must_env("JIRA_EMAIL"),
            api_token=must_env("JIRA_API_TOKEN"),
            project_key=must_env("JIRA_PROJECT_KEY"),
        ),
        telegram=TelegramClient(
            token=must_env("TELEGRAM_TOKEN"),
            chat_id=must_env("TELEGRAM_CHAT_ID"),
        ),
        github=GitHubClient(
            token=must_env("GITHUB_TOKEN"),
            repo=must_env("GITHUB_REPO"),
        ),
        anthropic_client=anthropic.Anthropic(api_key=must_env("ANTHROPIC_API_KEY")),
        target_deployment=os.environ.get("TARGET_DEPLOYMENT", "arithmetic-api"),
        target_namespace=os.environ.get("TARGET_NAMESPACE", "default"),
        target_image=os.environ.get("TARGET_IMAGE", "go-arithmetic-api:latest"),
        github_token=must_env("GITHUB_TOKEN"),
        github_repo=must_env("GITHUB_REPO"),
    )

    logger.info(f"Remediation agent started — polling every {POLL_INTERVAL.seconds}s")

    while True:
        try:
            agent.run_cycle()
        except Exception as exc:
            logger.error(f"Cycle failed: {exc}")
        time.sleep(POLL_INTERVAL.total_seconds())


if __name__ == "__main__":
    main()
