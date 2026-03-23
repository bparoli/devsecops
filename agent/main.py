import logging
import os
import time

from agent import POLL_INTERVAL, DiagnosticAgent

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
    agent = DiagnosticAgent(
        loki_url=os.environ.get("LOKI_URL", "http://loki.monitoring:3100"),
        telegram_token=must_env("TELEGRAM_TOKEN"),
        telegram_chat_id=must_env("TELEGRAM_CHAT_ID"),
        anthropic_api_key=must_env("ANTHROPIC_API_KEY"),
    )

    logger.info(f"Diagnostic agent started — polling every {POLL_INTERVAL.seconds}s")

    while True:
        try:
            agent.check_and_diagnose()
        except Exception as exc:
            logger.error(f"Check failed: {exc}")
        time.sleep(POLL_INTERVAL.total_seconds())


if __name__ == "__main__":
    main()
