"""Outreach draft entity grounded in verified facts."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.campaign import Campaign
    from app.db.models.company import Company
    from app.db.models.review import ReviewDecision


class OutreachDraft(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Evidence-grounded personalized outreach draft requiring human review."""

    __tablename__ = "outreach_drafts"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    claims_used: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    unsupported_claims: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(50), default="pending_review", nullable=False
    )  # pending_review, approved, edited, rejected

    # Relationships
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="drafts")
    company: Mapped["Company"] = relationship("Company", back_populates="drafts")
    review_decisions: Mapped[list["ReviewDecision"]] = relationship(
        "ReviewDecision", back_populates="draft", cascade="all, delete-orphan"
    )
