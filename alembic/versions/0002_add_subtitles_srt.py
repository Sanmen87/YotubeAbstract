"""add subtitles_srt to results

Revision ID: 0002_add_subtitles_srt
Revises: 0001_init
Create Date: 2026-02-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_subtitles_srt"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("results", sa.Column("subtitles_srt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("results", "subtitles_srt")
