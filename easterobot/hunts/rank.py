"""Manage egg hunting rankings and hunter records."""

from dataclasses import dataclass

from sqlalchemy import and_, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.config import agree
from easterobot.models import Egg

RANK_MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


@dataclass
class Hunter:
    """Represent a hunter with id, rank, and egg count."""

    member_id: int
    rank: int
    eggs: int

    @property
    def badge(self) -> str:
        """Return the badge emoji or rank number as a string."""
        return RANK_MEDAL.get(self.rank, f"`#{self.rank}`")

    @property
    def record(self) -> str:
        """Return formatted string showing badge, user mention, and eggs."""
        return (
            f"{self.badge} <@{self.member_id}>\n"
            f"\u2004\u2004\u2004\u2004\u2004"
            f"➥ {agree('{0} œuf', '{0} œufs', self.eggs)}"
        )


class Ranking:
    """Manage a collection of hunters and their rankings."""

    def __init__(self, hunters: list[Hunter]) -> None:
        """Create a ranking from a list of hunters.

        Args:
            hunters: A list of Hunter objects to include in the ranking.
        """
        self.hunters = hunters

    def all(self) -> list[Hunter]:
        """Return the full list of hunters.

        Returns:
            A list of all Hunter objects in the ranking.
        """
        return self.hunters

    def over(self, min_eggs: int) -> list[Hunter]:
        """Return hunters who have collected at least min_eggs.

        Args:
            min_eggs: The minimum eggs a hunter must have to be included.

        Returns:
            A list of hunters meeting or exceeding the egg count threshold.
        """
        return [hunter for hunter in self.hunters if hunter.eggs >= min_eggs]

    def page(self, page_number: int, *, limit: int) -> list[Hunter]:
        """Return hunters on the specified page with given page size.

        Args:
            page_number: The zero-based page number to retrieve.
            limit: The number of hunters per page.

        Returns:
            A list of hunters on the requested page. Returns an empty list if
            page_number or limit is negative.
        """
        if page_number < 0 or limit < 0:
            return []
        start = limit * page_number
        end = limit * (page_number + 1)
        return self.hunters[start:end]

    def count_page(self, page_size: int) -> int:
        """Calculate the total number of pages given a page size.

        Args:
            page_size: The number of hunters per page.

        Returns:
            The total number of pages needed to show all hunters.

        Examples:
            >>> Ranking([Hunter(1, 1, 3), Hunter(2, 2, 2)]).count_page(10)
            1
            >>> Ranking([]).count_page(10)
            0
            >>> Ranking([
            ...     Hunter(i, i, 20 - i) for i in range(10)
            ... ]).count_page(10)
            1
            >>> Ranking([
            ...     Hunter(i, i, 20 - i) for i in range(11)
            ... ]).count_page(10)
            2
        """
        if not self.hunters:
            return 0
        return (len(self.hunters) - 1) // page_size + 1

    def get(self, member_id: int) -> Hunter:
        """Return the hunter with the given member_id or a default hunter.

        Args:
            member_id: The ID of the member to retrieve.

        Returns:
            The Hunter matching member_id, or a default Hunter if not found.
        """
        for hunter in self.hunters:
            if hunter.member_id == member_id:
                return hunter
        lower_rank = min(len(self.hunters), 1)
        return Hunter(member_id, lower_rank, 0)

    @staticmethod
    async def from_guild(
        session: AsyncSession,
        guild_id: int,
        *,
        unlock_only: bool = False,
    ) -> "Ranking":
        """Fetch and build rankings for a guild from the database.

        Args:
            session: The async database session to use for the query.
            guild_id: The ID of the guild to fetch rankings for.
            unlock_only: If True, only include eggs that are unlocked.

        Returns:
            A Ranking object containing hunters ranked by their egg counts.
        """
        base_condition = Egg.guild_id == guild_id
        if unlock_only:
            base_condition = and_(base_condition, not_(Egg.lock))

        query = (
            select(
                Egg.user_id,
                func.rank().over(order_by=func.count().desc()).label("row"),
                func.count().label("count"),
            )
            .where(base_condition)
            .group_by(Egg.user_id)
            .order_by(func.count().desc())
        )

        result = await session.execute(query)
        hunters = [
            Hunter(member_id=user_id, rank=rank, eggs=egg_count)
            for user_id, rank, egg_count in result.all()
        ]
        return Ranking(hunters)
