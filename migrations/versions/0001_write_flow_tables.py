"""write-flow tables: proposals + transactional outbox

Revision ID: 0001
Revises:
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_write_proposals",
        sa.Column("proposal_id", sa.String(), primary_key=True),
        sa.Column("deployment_id", sa.String(), nullable=False),
        sa.Column("manifest_digest", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.Column("params_hash", sa.String(), nullable=False),
        sa.Column("diff", sa.String(), nullable=False, server_default=""),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING_APPROVAL"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
    )
    op.create_table(
        "agent_write_outbox",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("proposal_id", sa.String(), nullable=False, index=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("intent_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("agent_write_outbox")
    op.drop_table("agent_write_proposals")
