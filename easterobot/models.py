"""Module for models."""

from sqlalchemy import BigInteger, Boolean, Integer
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)

DISCORD_URL = "https://discord.com/channels"


class Base(DeclarativeBase):
    pass


class Egg(Base):
    __tablename__ = "egg"
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    guild_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    emoji_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    lock: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def jump_url(self) -> str:
        """Url to jump to the egg."""
        guild_id = self.guild_id or "@me"
        return f"{DISCORD_URL}/{guild_id}/{self.channel_id}/{self.id}"


class Hunt(Base):
    __tablename__ = "hunt"
    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    next_egg: Mapped[float] = mapped_column(default=0.0)

    @property
    def jump_url(self) -> str:
        """Url to jump to an hunt."""
        guild_id = self.guild_id or "@me"
        return f"{DISCORD_URL}/{guild_id}/{self.channel_id}"


class Cooldown(Base):
    __tablename__ = "cooldown"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    command: Mapped[str] = mapped_column(primary_key=True)
    timestamp: Mapped[float] = mapped_column(default=0.0)
