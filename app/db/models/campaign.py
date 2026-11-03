"""Campaign and CampaignCompany relationship models."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.draft import OutreachDraft
    from app.db.models.qualification import Qualification


class Campaign(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Represents a bounded GTM campaign experiment with target ICP criteria."""

    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_description: Mapped[str] = mapped_column(Text, nullable=False)
    icp_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    rubric_version: Mapped[str] = mapped_column(String(50), nullable=False, default="v1")

    # Relationships
    companies: Mapped[list["CampaignCompany"]] = relationship(
        "CampaignCompany", back_populates="campaign", cascade="all, delete-orphan"
    )
    qualifications: Mapped[list["Qualification"]] = relationship(
        "Qualification", back_populates="campaign", cascade="all, delete-orphan"
    )
    drafts: Mapped[list["OutreachDraft"]] = relationship(
        "OutreachDraft", back_populates="campaign", cascade="all, delete-orphan"
    )


class CampaignCompany(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Association between a campaign and an account record."""

    __tablename__ = "campaign_companies"
    __table_args__ = (UniqueConstraint("campaign_id", "company_id", name="uq_campaign_company"),)

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_import_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)

    # Relationships
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="companies")
    company: Mapped["Company"] = relationship("Company", back_populates="campaign_associations")
