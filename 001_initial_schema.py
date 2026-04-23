"""Initial schema — firewall_logs table

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "firewall_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("prompt_preview", sa.Text, nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("allowed", sa.Boolean, nullable=False),
        sa.Column("input_threat_level", sa.String(16), nullable=False),
        sa.Column("input_threats", JSON, nullable=True),
        sa.Column("input_ml_score", sa.Float, nullable=True),
        sa.Column("output_threat_level", sa.String(16), nullable=True),
        sa.Column("output_issues", JSON, nullable=True),
        sa.Column("latency_ms", sa.Float, nullable=False),
        sa.Column("meta", JSON, nullable=True),
    )

    # Indexes for common dashboard queries
    op.create_index("ix_firewall_logs_request_id",  "firewall_logs", ["request_id"], unique=True)
    op.create_index("ix_firewall_logs_created_at",  "firewall_logs", ["created_at"])
    op.create_index("ix_firewall_logs_allowed",     "firewall_logs", ["allowed"])
    op.create_index("ix_firewall_logs_threat_level","firewall_logs", ["input_threat_level"])


def downgrade() -> None:
    op.drop_table("firewall_logs")
