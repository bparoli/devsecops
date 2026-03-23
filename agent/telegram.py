import httpx


class TelegramClient:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.client = httpx.Client(timeout=10)

    def send(self, message: str) -> None:
        resp = self.client.get(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            params={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
            },
        )
        resp.raise_for_status()
