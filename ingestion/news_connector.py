"""Financial news connector interface; no provider is configured yet."""


class NewsConnector:
    """Placeholder interface for a licensed financial news provider."""

    def fetch_articles(self) -> list[dict[str, object]]:
        """Fetch articles after provider terms and API access are verified."""
        raise NotImplementedError("News source access is not configured")
