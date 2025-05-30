"""init database.

Revision ID: 2f0d4305e320
Revises:
Create Date: 2025-04-19 12:04:53.107440

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f0d4305e320"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "cooldown",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("command", sa.String(), nullable=False),
        sa.Column("timestamp", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "guild_id", "command"),
    )
    op.create_table(
        "egg",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("emoji_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_egg_guild_id"), "egg", ["guild_id"], unique=False)
    op.create_index(op.f("ix_egg_user_id"), "egg", ["user_id"], unique=False)
    op.create_table(
        "hunt",
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("next_egg", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("channel_id"),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("hunt")
    op.drop_index(op.f("ix_egg_user_id"), table_name="egg")
    op.drop_index(op.f("ix_egg_guild_id"), table_name="egg")
    op.drop_table("egg")
    op.drop_table("cooldown")
    # ### end Alembic commands ###
