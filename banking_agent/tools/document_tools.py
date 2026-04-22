"""
document_tools.py
-----------------
Deterministic rule-based tools for KYC document compliance checking.

Each account type has a defined list of required documents. These rules
are regulatory requirements — not configurable by the LLM.
"""

from __future__ import annotations

import json
from typing import List

# Required KYC documents per account type
_REQUIRED_DOCS: dict[str, List[str]] = {
    "personal_checking": [
        "government_id",
        "proof_of_address",
        "proof_of_income",
    ],
    "personal_savings": [
        "government_id",
        "proof_of_address",
    ],
    "business_current": [
        "company_registration",
        "certificate_of_incorporation",
        "proof_of_business_address",
        "director_ids",
        "ubo_declaration",
        "bank_statements_6months",
    ],
    "business_savings": [
        "company_registration",
        "certificate_of_incorporation",
        "proof_of_business_address",
        "director_ids",
        "ubo_declaration",
    ],
    "investment": [
        "government_id",
        "proof_of_address",
        "proof_of_income",
        "source_of_funds_declaration",
        "tax_identification_number",
    ],
}

# Human-readable document name mapping for follow-up messages
_DOC_DISPLAY_NAMES: dict[str, str] = {
    "government_id": "Government-issued photo ID (passport, national ID, or driver's license)",
    "proof_of_address": "Proof of address (utility bill, bank statement, or council tax letter, dated within 3 months)",
    "proof_of_income": "Proof of income (recent payslips, employer letter, or tax return)",
    "company_registration": "Company registration certificate",
    "certificate_of_incorporation": "Certificate of incorporation",
    "proof_of_business_address": "Proof of business address (utility bill or lease agreement)",
    "director_ids": "Government-issued ID for each company director",
    "ubo_declaration": "Ultimate Beneficial Owner (UBO) declaration form",
    "bank_statements_6months": "Six months of business bank statements",
    "source_of_funds_declaration": "Source of funds declaration (signed statement explaining the origin of investment funds)",
    "tax_identification_number": "Tax Identification Number (TIN) document",
}


def get_required_kyc_documents(account_type: str) -> dict:
    """Return the list of required KYC documents for a given account type."""
    account_type = account_type.lower().strip()
    required = _REQUIRED_DOCS.get(account_type)
    if required is None:
        return {
            "status": "error",
            "error": f"Unknown account type '{account_type}'. "
                     f"Must be one of: {', '.join(_REQUIRED_DOCS)}.",
        }
    display = [_DOC_DISPLAY_NAMES.get(d, d) for d in required]
    return {
        "status": "success",
        "account_type": account_type,
        "required_documents": required,
        "required_documents_display": display,
    }


def check_kyc_documents(account_type: str, documents_provided: str) -> dict:
    """
    Compare submitted KYC documents against the required list and identify gaps.

    Args:
        account_type: The account type being applied for.
        documents_provided: JSON array string or comma-separated list of submitted document names.

    Returns:
        A dict with required_documents, provided_documents, missing_documents,
        all_present, and a followup_request message if any docs are missing.
    """
    account_type = account_type.lower().strip()
    required = _REQUIRED_DOCS.get(account_type)
    if required is None:
        return {
            "status": "error",
            "error": f"Unknown account type '{account_type}'.",
        }

    try:
        provided: List[str] = json.loads(documents_provided)
    except (json.JSONDecodeError, TypeError):
        provided = [d.strip() for d in str(documents_provided).split(",") if d.strip()]

    provided_normalised = {d.lower().replace(" ", "_") for d in provided}
    missing = [d for d in required if d.lower().replace(" ", "_") not in provided_normalised]

    followup_request: str | None = None
    if missing:
        missing_display = [_DOC_DISPLAY_NAMES.get(d, d) for d in missing]
        followup_request = (
            "To complete your KYC verification, we require the following additional documents:\n"
            + "\n".join(f"  • {doc}" for doc in missing_display)
            + "\n\nPlease provide these documents at your earliest convenience to proceed with your application."
        )

    return {
        "status": "success",
        "account_type": account_type,
        "required_documents": required,
        "provided_documents": list(provided),
        "missing_documents": missing,
        "all_present": len(missing) == 0,
        "followup_request": followup_request,
    }
