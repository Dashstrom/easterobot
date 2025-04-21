"""Test search command."""

from math import isclose

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.config import MConfig
from easterobot.hunts.hunt import HuntQuery
from easterobot.models import Egg
from tests.constants import (
    CHANNEL_ID,
    EMOJI_ID,
    GUILD_ID,
    USER_ID_1,
    USER_ID_2,
    USER_ID_3,
)


@pytest.mark.asyncio
async def test_luck(session: AsyncSession, config: MConfig) -> None:
    """Test the luck configuration."""
    hunt = HuntQuery(config)
    for user_id, egg_count in (
        (USER_ID_1, 0),
        (USER_ID_2, 15),
        (USER_ID_3, 30),
    ):
        for _ in range(egg_count):
            session.add(
                Egg(
                    guild_id=GUILD_ID,
                    channel_id=CHANNEL_ID,
                    user_id=user_id,
                    emoji_id=EMOJI_ID,
                )
            )
        await session.commit()
    N = 10_000  # noqa: N806
    for user_id, egg_count, luck, discovered, spotted in (
        (USER_ID_1, 0, 1.0, 1.0, 0.0),
        (USER_ID_2, 15, 0.5, 0.75, 0.4995),
        (USER_ID_3, 30, 0.0, 0.6, 0.666),
    ):
        member_luck = await hunt.get_luck(session, GUILD_ID, user_id)
        assert member_luck.egg_count == egg_count
        assert isclose(member_luck.luck, luck)
        assert isclose(member_luck.discovered, discovered)
        assert isclose(member_luck.spotted, spotted)
        prob_d = sum(member_luck.sample_discovered() for _ in range(N)) / N
        prob_s = sum(member_luck.sample_spotted() for _ in range(N)) / N
        assert isclose(prob_d, discovered, rel_tol=5e-2)
        assert isclose(prob_s, spotted, rel_tol=5e-2)
