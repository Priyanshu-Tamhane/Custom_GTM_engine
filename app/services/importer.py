"""CSV Import and deduplication service for company records and campaign associations."""

import csv
import io
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.import_job import ImportSummaryResponse, RowError
from app.core.exceptions import EntityNotFoundError, ValidationError
from app.core.logging import logger
from app.db.models.campaign import Campaign, CampaignCompany
from app.db.models.company import Company
from app.services.normalizer import normalize_domain

# Flexible column header mappings (case-insensitive)
HEADER_MAPPINGS = {
    "company_name": ("company_name", "company", "name", "organization"),
    "domain": ("domain", "website", "url", "company_domain", "web"),
    "industry": ("industry", "sector", "vertical"),
    "employee_count": ("employee_count", "employees", "size", "headcount", "employee_range"),
    "source_url": ("source_url", "source", "evidence_url"),
    "notes": ("notes", "description", "note", "comment"),
}


class CSVImportService:
    """Parses, validates, normalizes, and deduplicates CSV company lists."""

    @staticmethod
    def _map_headers(fieldnames: list[str]) -> dict[str, str]:
        """Maps CSV headers to canonical field names."""
        normalized_headers = {h.strip().lower(): h for h in fieldnames if h}
        mapped: dict[str, str] = {}

        for canonical, aliases in HEADER_MAPPINGS.items():
            for alias in aliases:
                if alias in normalized_headers:
                    mapped[canonical] = normalized_headers[alias]
                    break

        return mapped

    @classmethod
    def import_from_csv_content(
        cls,
        db: Session,
        campaign_id: uuid.UUID,
        csv_text: str,
        source_import_id: str | None = None,
    ) -> ImportSummaryResponse:
        """Parse and import companies from raw CSV string content.

        Args:
            db: Active database session.
            campaign_id: Target campaign UUID.
            csv_text: Full CSV file content as string.
            source_import_id: Optional audit identifier for this batch.

        Returns:
            ImportSummaryResponse with counts, attached IDs, and row errors.

        Raises:
            EntityNotFoundError: If campaign_id does not exist.
            ValidationError: If CSV file is empty or missing required headers.
        """
        # Verify campaign exists
        campaign = db.scalar(select(Campaign).where(Campaign.id == campaign_id))
        if not campaign:
            raise EntityNotFoundError(f"Campaign with ID {campaign_id} not found")

        if not csv_text or not csv_text.strip():
            raise ValidationError("CSV content is empty")

        import_id = source_import_id or f"imp_{uuid.uuid4().hex[:12]}"

        # Read CSV rows
        f = io.StringIO(csv_text.strip())
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValidationError("CSV file contains no header row")

        header_map = cls._map_headers(reader.fieldnames)

        # Enforce required columns: domain and company_name
        if "domain" not in header_map:
            raise ValidationError(
                f"Missing required 'domain' column. Found columns: {reader.fieldnames}"
            )

        total_rows = 0
        accepted_count = 0
        duplicates_in_file_count = 0
        duplicates_existing_count = 0
        rejected_count = 0

        seen_domains_in_file: set[str] = set()
        attached_company_ids: list[uuid.UUID] = []
        row_errors: list[RowError] = []

        domain_col = header_map["domain"]
        company_name_col = header_map.get("company_name")
        industry_col = header_map.get("industry")
        employee_col = header_map.get("employee_count")
        notes_col = header_map.get("notes")

        for idx, row in enumerate(reader, start=1):
            total_rows += 1
            raw_domain = row.get(domain_col, "").strip() if domain_col else ""
            raw_company_name = row.get(company_name_col, "").strip() if company_name_col else ""

            # Validation: company_name check
            if company_name_col and not raw_company_name:
                row_errors.append(
                    RowError(
                        row_number=idx,
                        raw_domain=raw_domain,
                        raw_company_name=raw_company_name,
                        reason="Missing company name",
                    )
                )
                rejected_count += 1
                continue

            # Validation: domain normalization
            try:
                norm_domain = normalize_domain(raw_domain)
            except ValidationError as exc:
                row_errors.append(
                    RowError(
                        row_number=idx,
                        raw_domain=raw_domain,
                        raw_company_name=raw_company_name,
                        reason=exc.message,
                    )
                )
                rejected_count += 1
                continue

            # In-file deduplication
            if norm_domain in seen_domains_in_file:
                duplicates_in_file_count += 1
                continue

            seen_domains_in_file.add(norm_domain)

            # Validation: optional employee_count parsing
            emp_range_str: str | None = None
            if employee_col:
                raw_emp = row.get(employee_col, "").strip()
                if raw_emp:
                    try:
                        emp_int = int(raw_emp)
                        if emp_int < 0:
                            raise ValueError()
                        emp_range_str = str(emp_int)
                    except ValueError:
                        row_errors.append(
                            RowError(
                                row_number=idx,
                                raw_domain=raw_domain,
                                raw_company_name=raw_company_name,
                                reason=f"Invalid employee count: '{raw_emp}' must be a non-negative integer",
                            )
                        )
                        rejected_count += 1
                        continue

            industry_val = row.get(industry_col, "").strip() if industry_col else None
            notes_val = row.get(notes_col, "").strip() if notes_col else None
            display_name = raw_company_name or norm_domain

            # Database deduplication: check if Company already exists
            existing_company = db.scalar(
                select(Company).where(Company.normalized_domain == norm_domain)
            )

            if existing_company:
                company = existing_company
                is_brand_new = False
            else:
                company = Company(
                    normalized_domain=norm_domain,
                    company_name=display_name,
                    industry=industry_val or None,
                    employee_range=emp_range_str,
                    description=notes_val or None,
                    record_status="imported",
                )
                db.add(company)
                db.flush()
                is_brand_new = True

            # Campaign association: check if already attached
            existing_assoc = db.scalar(
                select(CampaignCompany).where(
                    CampaignCompany.campaign_id == campaign_id,
                    CampaignCompany.company_id == company.id,
                )
            )

            if not existing_assoc:
                association = CampaignCompany(
                    campaign_id=campaign_id,
                    company_id=company.id,
                    source_import_id=import_id,
                    status="pending",
                )
                db.add(association)

            if company.id not in attached_company_ids:
                attached_company_ids.append(company.id)

            if is_brand_new:
                accepted_count += 1
            else:
                duplicates_existing_count += 1

        db.commit()

        logger.info(
            f"Import {import_id} for campaign {campaign_id} completed: "
            f"{accepted_count} created, {duplicates_existing_count} reused, "
            f"{duplicates_in_file_count} in-file duplicates skipped, {rejected_count} rejected.",
            extra_fields={"campaign_id": str(campaign_id), "source_import_id": import_id},
        )

        return ImportSummaryResponse(
            campaign_id=campaign_id,
            source_import_id=import_id,
            total_rows=total_rows,
            accepted=accepted_count,
            duplicates_in_file_skipped=duplicates_in_file_count,
            duplicates_existing_associated=duplicates_existing_count,
            rejected=rejected_count,
            company_ids=attached_company_ids,
            row_errors=row_errors,
        )
