from typing import Optional

from sqlalchemy.orm import (  # type: ignore
    DeclarativeBase,
    Mapped,
    mapped_column,
)


class Base(DeclarativeBase):  # type: ignore
    pass


class Egg(Base):
    __tablename__ = "egg"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(nullable=False)
    channel_id: Mapped[int] = mapped_column(nullable=False)
    user_id: Mapped[int] = mapped_column(nullable=False)
    emoji_id: Mapped[int] = mapped_column(nullable=False)
    message_id: Mapped[Optional[int]] = mapped_column(
        nullable=True, default=None
    )


class Hunt(Base):
    __tablename__ = "hunt"
    channel_id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(nullable=False)
    next_egg: Mapped[float] = mapped_column(default=0.0)


class Hunter(Base):
    __tablename__ = "hunter"
    user_id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(primary_key=True)
    last_search: Mapped[float] = mapped_column(default=0.0)
