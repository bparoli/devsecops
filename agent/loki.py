import httpx
from datetime import datetime, timedelta, timezone


class LokiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.Client(timeout=10)

    def query_errors(self, since: timedelta) -> list[str]:
        """Return error log lines from arithmetic-api in the last `since` duration."""
        now = datetime.now(timezone.utc)
        start = now - since

        # Match both JSON format ({"level":"ERROR"}) and Go text format (ERROR keyword)
        query = '{job="kubernetes-pods", filename=~".*/default_arithmetic-api.*"} |~ `"level":"ERROR"|\\sERROR\\s`'

        resp = self.client.get(
            f"{self.base_url}/loki/api/v1/query_range",
            params={
                "query": query,
                "start": int(start.timestamp() * 1e9),
                "end": int(now.timestamp() * 1e9),
                "limit": 50,
                "direction": "forward",
            },
        )
        resp.raise_for_status()

        lines = []
        for stream in resp.json()["data"]["result"]:
            for _ts, line in stream["values"]:
                lines.append(line)
        return lines
