"""Qualification entity storing explainable fit scores and evidence citations."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.campaign import Campaign
    from app.db.models.company import Company
    from app.db.models.review import ReviewDecision


class Qualification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Explainable ICP fit score evaluation backed by source evidence."""

    __tablename__ = "qualifications"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(50), default="scored", nullable=False
    )  # scored, needs_review, disqualified

    # Relationships
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="qualifications")
    company: Mapped["Company"] = relationship("Company", back_populates="qualifications")
    review_decisions: Mapped[list["ReviewDecision"]] = relationship(
        "ReviewDecision", back_populates="qualification", cascade="all, delete-orphan"
    )
