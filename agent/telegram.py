import httpx


class TelegramClient:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.client = httpx.Client(timeout=10)

    def get_updates(self, offset: int = 0) -> list[dict]:
        """Return new updates from this chat since offset."""
        resp = self.client.get(
            f"https://api.telegram.org/bot{self.token}/getUpdates",
            params={"offset": offset, "timeout": 1},
        )
        resp.raise_for_status()
        updates = resp.json().get("result", [])
        return [
            u for u in updates
            if str(u.get("message", {}).get("chat", {}).get("id", "")) == str(self.chat_id)
        ]

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
