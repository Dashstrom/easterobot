"""Module config."""

from easterobot.bot import EXAMPLE_CONFIG_PATH
from easterobot.config import MConfig, dump_yaml, load_yaml


def test_load_config() -> None:
    """Test load config."""
    config = load_yaml(EXAMPLE_CONFIG_PATH.read_bytes(), MConfig)
    data = dump_yaml(config)
    assert isinstance(config.token, str)
    assert data
