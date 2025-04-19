"""Module config."""

from easterobot.bot import EXAMPLE_CONFIG_PATH
from easterobot.config import (
    load_config_from_path,
)


def test_load_config() -> None:
    """Test load config."""
    config = load_config_from_path(EXAMPLE_CONFIG_PATH)
    assert isinstance(config.token, str)
