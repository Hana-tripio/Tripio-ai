"""add place sync fields

Revision ID: 20260617_0002
Revises: 20260616_0001
Create Date: 2026-06-17 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260617_0002"
down_revision: str | None = "20260616_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column("sync_status", sa.String(length=30), nullable=False, server_default="RAW"),
    )
    op.add_column(
        "places",
        sa.Column("canonical_place_key", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "places",
        sa.Column("review_reason", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column("places", sa.Column("backend_place_id", sa.BigInteger(), nullable=True))
    op.add_column("places", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "places",
        sa.Column("sync_error_message", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("idx_places_sync_status", "places", ["sync_status"])


def downgrade() -> None:
    op.drop_index("idx_places_sync_status", table_name="places")
    op.drop_column("places", "sync_error_message")
    op.drop_column("places", "last_synced_at")
    op.drop_column("places", "backend_place_id")
    op.drop_column("places", "review_reason")
    op.drop_column("places", "canonical_place_key")
    op.drop_column("places", "sync_status")
