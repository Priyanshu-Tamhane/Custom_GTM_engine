"""Company account canonical entity."""

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.campaign import CampaignCompany
    from app.db.models.draft import OutreachDraft
    from app.db.models.enrichment import EnrichmentRun
    from app.db.models.evidence import SourceEvidence
    from app.db.models.qualification import Qualification


class Company(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Canonical company record keyed by unique normalized domain."""

    __tablename__ = "companies"

    normalized_domain: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employee_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_status: Mapped[str] = mapped_column(
        String(50), default="imported", nullable=False
    )  # imported, enriching, enriched, qualified, review_ready, archived

    # Relationships
    campaign_associations: Mapped[list["CampaignCompany"]] = relationship(
        "CampaignCompany", back_populates="company", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["SourceEvidence"]] = relationship(
        "SourceEvidence", back_populates="company", cascade="all, delete-orphan"
    )
    enrichment_runs: Mapped[list["EnrichmentRun"]] = relationship(
        "EnrichmentRun", back_populates="company", cascade="all, delete-orphan"
    )
    qualifications: Mapped[list["Qualification"]] = relationship(
        "Qualification", back_populates="company", cascade="all, delete-orphan"
    )
    drafts: Mapped[list["OutreachDraft"]] = relationship(
        "OutreachDraft", back_populates="company", cascade="all, delete-orphan"
    )
