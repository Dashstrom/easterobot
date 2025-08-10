"""Locking mechanism for eggs in the database.

This module provides asynchronous context management and helper
functions for retrieving, locking, deleting, and updating `Egg`
records in the database. It ensures that concurrent access to
eggs within the same guild is properly synchronized.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from types import TracebackType
from typing import ClassVar, Optional, final

import discord
from sqlalchemy import and_, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.config import agree
from easterobot.models import Egg

logger = logging.getLogger(__name__)


async def fetch_unlocked_eggs(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    limit_count: int,
) -> list[Egg]:
    """Retrieve a random set of unlocked eggs for a specific user.

    Args:
        session: Active asynchronous SQLAlchemy session.
        guild_id: The guild ID to search in.
        user_id: The user ID whose eggs should be fetched.
        limit_count: The maximum number of eggs to retrieve.

    Returns:
        A list of `Egg` objects matching the criteria.
    """
    return list(
        (
            await session.scalars(
                select(Egg)
                .where(
                    and_(
                        Egg.guild_id == guild_id,
                        Egg.user_id == user_id,
                        not_(Egg.lock),
                    )
                )
                .order_by(func.random())  # Randomize retrieval
                .limit(limit_count)
            )
        ).all()
    )


async def fetch_unlocked_egg_count(
    session: AsyncSession,
    guild_id: int,
    user_ids: Iterable[int],
) -> dict[int, int]:
    """Retrieve the number of unlocked eggs for multiple users.

    Args:
        session: Active asynchronous SQLAlchemy session.
        guild_id: The guild ID to search in.
        user_ids: Iterable of user IDs to check.

    Returns:
        A dictionary mapping each user ID to their count of unlocked eggs.
        Users with no eggs will have a count of 0.
    """
    user_ids = list(user_ids)
    res = await session.execute(
        select(Egg.user_id, func.count().label("count"))
        .where(
            and_(
                Egg.guild_id == guild_id,
                Egg.user_id.in_(user_ids),
                not_(Egg.lock),
            )
        )
        .group_by(Egg.user_id)
    )
    result = dict(res.all())  # type: ignore[arg-type]
    for uid in user_ids:
        if uid not in result:
            result[uid] = 0
    return result


class EggLockerError(Exception):
    """Raised when egg locking constraints cannot be met."""


@final
class EggLocker(AbstractAsyncContextManager["EggLocker"]):
    """Synchronize egg operations for a specific guild."""

    # One lock per guild to prevent concurrent modifications
    _guild_locks: ClassVar[dict[int, asyncio.Lock]] = {}

    def __init__(self, session: AsyncSession, guild_id: int) -> None:
        """Initialize the locker for a given guild.

        Args:
            session: Active asynchronous SQLAlchemy session.
            guild_id: The guild ID to apply locking to.
        """
        self._session = session
        self._guild_id = guild_id
        self._eggs: list[Egg] = []

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Acquire the guild lock and commit at the end of the block."""
        if self._guild_id not in self._guild_locks:
            self._guild_locks[self._guild_id] = asyncio.Lock()
        async with self._guild_locks[self._guild_id]:
            yield
            await self._session.commit()

    async def get(
        self,
        member: discord.Member,
        egg_count: int,
    ) -> list[Egg]:
        """Lock a given number of unlocked eggs for a member.

        Args:
            member: The Discord member requesting eggs.
            egg_count: Number of eggs to lock.

        Returns:
            A list of locked `Egg` objects.

        Raises:
            EggLockerError: If there are fewer eggs available than requested.
        """
        eggs = await fetch_unlocked_eggs(
            self._session,
            self._guild_id,
            member.id,
            egg_count,
        )
        if len(eggs) < egg_count:
            egg_text = agree("œuf", "œufs", len(eggs))
            msg = (
                f"{member.mention} n'a plus que {len(eggs)} {egg_text} "
                f"disponible sur les {egg_count} demandés"
            )
            raise EggLockerError(msg)
        for egg in eggs:
            egg.lock = True
        self._eggs.extend(eggs)
        logger.info(
            "Locked %s egg(s) for %s (%s)",
            len(eggs),
            member.name,
            member.id,
        )
        return eggs

    async def delete(self, eggs: Iterable[Egg]) -> None:
        """Remove eggs from the database and locker.

        Args:
            eggs: Iterable of `Egg` objects to delete.
        """
        tasks = []
        for egg in eggs:
            self._eggs.remove(egg)
            tasks.append(self._session.delete(egg))
        await asyncio.gather(*tasks)

    def update(self, eggs: Iterable[Egg]) -> None:
        """Add or update eggs in the locker and database session.

        Args:
            eggs: Iterable of `Egg` objects to add or update.
        """
        for egg in eggs:
            self._eggs.append(egg)
            self._session.add(egg)

    async def pre_check(
        self,
        members: dict[discord.Member, int],
    ) -> None:
        """Ensure each member has enough unlocked eggs before locking.

        Args:
            members: Mapping of members to the number of eggs they need.

        Raises:
            EggLockerError: If any member has fewer eggs than required.
        """
        if not members:
            return
        member_ids = {member.id: member for member in members}
        counter = await fetch_unlocked_egg_count(
            self._session,
            self._guild_id,
            member_ids,
        )
        for user_id, available in counter.items():
            member = member_ids[user_id]
            required = members[member]
            if available < required:
                egg_text = agree("œuf", "œufs", available)
                msg = (
                    f"{member.mention} n'a que {available} {egg_text} "
                    f"disponible sur les {required} demandés"
                )
                raise EggLockerError(msg)

    async def __aenter__(self) -> "EggLocker":
        """Enter the async context and return this instance."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        """Release all locks and rollback any changes on exit."""
        async with self.transaction():
            await self._session.rollback()
            for egg in self._eggs:
                egg.lock = False
        return None
