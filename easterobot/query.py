"""Base class for managing query operations in a cog system."""

from easterobot.config import (
    MConfig,
)


class QueryManager:
    """Manages query operations with provided configuration."""

    def __init__(self, config: MConfig) -> None:
        """Initialize the QueryManager with a configuration.

        Args:
            config: Configuration object providing necessary settings.
        """
        self.config = config
