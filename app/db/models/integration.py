"""Integration event entity for export and outbound synchronizations."""

import uuid

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IntegrationEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Auditable log of external outbound integrations (CSV export, CRM sync)."""

    __tablename__ = "integration_events"

    destination: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # csv_export, hubspot, webhook
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # company, draft, batch
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(50), nullable=False)  # export, sync
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, succeeded, failed
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
