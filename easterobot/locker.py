"""Lock the module."""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from types import TracebackType
from typing import ClassVar, Optional, final

import discord
from sqlalchemy import and_, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import override

from easterobot.config import agree
from easterobot.models import Egg

logger = logging.getLogger(__name__)


async def fetch_unlocked_eggs(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    counter: int,
) -> list[Egg]:
    """Get the count of unlocked eggs."""
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
                .order_by(func.random())  # Randomize
                .limit(counter)
            )
        ).all()
    )


async def fetch_unlocked_egg_count(
    session: AsyncSession,
    guild_id: int,
    user_ids: Iterable[int],
) -> dict[int, int]:
    """Get the count of unlocked eggs."""
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
    for user_id in user_ids:
        if user_id not in result:
            result[user_id] = 0
    return result


class EggLockerError(Exception):
    pass


@final
class EggLocker(AbstractAsyncContextManager["EggLocker"]):
    # TODO(dashstrom): memory leak over time
    _guild_locks: ClassVar[dict[int, asyncio.Lock]] = {}

    def __init__(self, session: AsyncSession, guild_id: int) -> None:
        """Init EggLocker."""
        self._session = session
        self._guild_id = guild_id
        self._eggs: list[Egg] = []

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Return guild lock."""
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
        """Update the egg locker."""
        eggs = await fetch_unlocked_eggs(
            self._session,
            self._guild_id,
            member.id,
            egg_count,
        )
        if len(eggs) < egg_count:
            egg_text = agree("œuf", "œufs", len(eggs))
            error_message = (
                f"{member.mention} n'a plus que {len(eggs)} {egg_text} "
                f"disponible sur les {egg_count} demandés"
            )
            raise EggLockerError(error_message)
        for egg in eggs:
            egg.lock = True
        self._eggs.extend(eggs)
        logger.info(
            "Lock %s egg(s) of %s (%s)",
            len(eggs),
            member.name,
            member.id,
        )
        return eggs

    async def delete(self, eggs: Iterable[Egg]) -> None:
        """Delete eggs."""
        futures = []
        for egg in eggs:
            self._eggs.remove(egg)
            futures.append(self._session.delete(egg))
        await asyncio.gather(*futures)

    def update(self, eggs: Iterable[Egg]) -> None:
        """Update eggs."""
        for egg in eggs:
            self._eggs.append(egg)
            self._session.add(egg)

    async def pre_check(
        self,
        members: dict[discord.Member, int],
    ) -> None:
        """Return the list of invalid user."""
        if not members:
            return
        member_ids = {member.id: member for member in members}
        counter = await fetch_unlocked_egg_count(
            self._session,
            self._guild_id,
            member_ids,
        )
        for user_id, egg_count in counter.items():
            member = member_ids[user_id]
            required = members[member]
            if egg_count < required:
                egg_text = agree("œuf", "œufs", egg_count)
                error_message = (
                    f"{member.mention} n'a que {egg_count} {egg_text} "
                    f"disponible sur les {required} demandés"
                )
                raise EggLockerError(error_message)

    @override
    async def __aenter__(self) -> "EggLocker":
        """Return `self` upon entering the runtime context."""
        return self

    @override
    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        """Raise any exception triggered within the runtime context."""
        async with self.transaction():
            await self._session.rollback()
            for egg in self._eggs:
                egg.lock = False
        return None
