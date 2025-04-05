"""Configuration for all tests."""

from typing import Any

import pytest

from easterobot import __author__


@pytest.fixture(autouse=True)
def _add_author(doctest_namespace: dict[str, Any]) -> None:
    """Update doctest namespace."""
    doctest_namespace["author"] = __author__
