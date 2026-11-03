"""Human reviewer decisions and audit trail entity."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.draft import OutreachDraft
    from app.db.models.qualification import Qualification


class ReviewDecision(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Audit trail for human gate decisions (approve, edit, reject, re-enrich)."""

    __tablename__ = "review_decisions"

    draft_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outreach_drafts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    qualification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("qualifications.id", ondelete="CASCADE"), nullable=True, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # approved, edited, rejected, re_enrich_requested
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_content: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Relationships
    draft: Mapped["OutreachDraft | None"] = relationship(
        "OutreachDraft", back_populates="review_decisions"
    )
    qualification: Mapped["Qualification | None"] = relationship(
        "Qualification", back_populates="review_decisions"
    )
