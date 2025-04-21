"""Base class for cog query."""

from easterobot.config import (
    MConfig,
)


class QueryManager:
    def __init__(self, config: MConfig):
        """Instantiate QueryQueryManager."""
        self.config = config
