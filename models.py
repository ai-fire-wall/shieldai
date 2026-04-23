"""
ORM models — single table for the MVP.
Each row is one firewall transaction (prompt in, response out).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FirewallLog(Base):
    __tablename__ = "firewall_logs"

    # ── Identity ──────────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # ── Request metadata ──────────────────────────────────────────────────────
    prompt_preview: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=True)

    # ── Decision ──────────────────────────────────────────────────────────────
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)

    # ── Input analysis ────────────────────────────────────────────────────────
    input_threat_level: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True
    )
    input_threats: Mapped[list] = mapped_column(JSON, default=list)
    input_ml_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Output analysis ───────────────────────────────────────────────────────
    output_threat_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    output_issues: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # ── Performance ───────────────────────────────────────────────────────────
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)

    # ── Caller metadata (user_id, session_id, etc.) ───────────────────────────
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def to_dict(self) -> dict:
        return {
            "request_id":          self.request_id,
            "created_at":          self.created_at.isoformat(),
            "prompt_preview":      self.prompt_preview,
            "provider":            self.provider,
            "model":               self.model,
            "allowed":             self.allowed,
            "input_threat_level":  self.input_threat_level,
            "input_threats":       self.input_threats,
            "input_ml_score":      self.input_ml_score,
            "output_threat_level": self.output_threat_level,
            "output_issues":       self.output_issues,
            "latency_ms":          self.latency_ms,
        }
