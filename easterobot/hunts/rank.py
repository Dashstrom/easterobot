"""Start a run."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.config import agree
from easterobot.models import Egg

RANK_MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


@dataclass
class Hunter:
    member_id: int
    rank: int
    eggs: int

    @property
    def badge(self) -> str:
        """Get the ranking badge."""
        return RANK_MEDAL.get(self.rank, f"`#{self.rank}`")

    @property
    def record(self) -> str:
        """Get the records of eggs."""
        return (
            f"{self.badge} <@{self.member_id}>\n"
            f"\u2004\u2004\u2004\u2004\u2004"
            f"➥ {agree('{0} œuf', '{0} œufs', self.eggs)}"
        )


class Ranking:
    def __init__(self, hunters: list[Hunter]) -> None:
        """Initialise Ranking."""
        self.hunters = hunters

    def all(self) -> list[Hunter]:
        """Get all hunter."""
        return self.hunters

    def over(self, limit: int) -> list[Hunter]:
        """Get all hunter over limit."""
        return [h for h in self.hunters if h.eggs >= limit]

    def page(self, n: int, *, limit: int) -> list[Hunter]:
        """Get a hunters by page."""
        if n < 0 or limit < 0:
            return []
        return self.hunters[limit * n : limit * (n + 1)]

    def get(self, member_id: int) -> Hunter:
        """Get a hunter."""
        for hunter in self.hunters:
            if hunter.member_id == member_id:
                return hunter
        return Hunter(member_id, min(len(self.hunters), 1), 0)

    @staticmethod
    async def from_guild(
        session: AsyncSession,
        guild_id: int,
    ) -> "Ranking":
        """Get ranks by page."""
        query = (
            select(
                Egg.user_id,
                func.rank().over(order_by=func.count().desc()).label("row"),
                func.count().label("count"),
            )
            .where(Egg.guild_id == guild_id)
            .group_by(Egg.user_id)
            .order_by(func.count().desc())
        )
        res = await session.execute(query)
        hunters = [
            Hunter(member_id, rank, egg_count)
            for member_id, rank, egg_count in res.all()
        ]
        return Ranking(hunters)
