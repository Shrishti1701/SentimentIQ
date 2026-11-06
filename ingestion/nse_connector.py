"""NSE announcement connector interface.

Before implementing collection, verify NSE documentation, access conditions,
licensing, and permitted polling frequency. No endpoint is assumed here.
"""


class NSEConnector:
    """Placeholder interface for a compliant NSE announcement source."""

    def fetch_announcements(self) -> list[dict[str, object]]:
        """Fetch announcements once a verified source is configured."""
        raise NotImplementedError("NSE source access is not configured")
