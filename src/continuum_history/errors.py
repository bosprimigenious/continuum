"""Expected errors are explicit, never disguised as empty search results."""


class HistoryError(ValueError):
    """A safe, actionable domain error suitable for CLI/MCP responses."""
