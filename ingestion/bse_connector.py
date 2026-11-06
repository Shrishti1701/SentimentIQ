"""BSE announcement connector interface.

Verify official documentation, access conditions, licensing, and permitted
polling frequency before implementing collection. No endpoint is assumed.
"""


class BSEConnector:
    """Placeholder interface for a compliant BSE announcement source."""

    def fetch_announcements(self) -> list[dict[str, object]]:
        """Fetch announcements once a verified source is configured."""
        raise NotImplementedError("BSE source access is not configured")
