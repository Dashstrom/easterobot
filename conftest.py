"""Configuration for all tests."""

from collections.abc import AsyncIterator
from typing import Any

import py
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from easterobot import __author__
from easterobot.bot import Easterobot
from easterobot.config import MConfig


@pytest.fixture(autouse=True)
def _add_author(doctest_namespace: dict[str, Any]) -> None:
    """Update doctest namespace."""
    doctest_namespace["author"] = __author__


@pytest.fixture
def bot(tmpdir: py.path.LocalPath) -> Easterobot:
    """Get a bot ready-to-use."""
    return Easterobot.generate(str(tmpdir), env=True)


@pytest.fixture
def engine(bot: Easterobot) -> AsyncEngine:
    """Get a bot ready-to-use."""
    return bot.engine


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Get a bot ready-to-use."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def config(bot: Easterobot) -> MConfig:
    """Get a bot ready-to-use."""
    return bot.config
