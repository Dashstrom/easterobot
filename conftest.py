"""Configuration for all tests."""

from collections.abc import AsyncIterator
from typing import Any

import py
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from easterobot.bot import Easterobot
from easterobot.config import MConfig


@pytest.fixture(autouse=True)
def _add_bot(doctest_namespace: dict[str, Any], bot: Easterobot) -> None:
    """Update doctest namespace."""
    doctest_namespace["bot"] = bot
    doctest_namespace["engine"] = bot.engine
    doctest_namespace["config"] = bot.config


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
