"""
identity_tools.py
-----------------
Deterministic tools for identity verification and document validity checks.

In production these would call a third-party identity verification provider
(e.g. Onfido, Jumio, Trulioo). Here they use rule-based simulation that
flags common mismatches and expiry conditions.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List


def verify_identity(
    full_name: str,
    date_of_birth: str,
    id_type: str,
    id_number: str,
    id_expiry_date: str,
    nationality: str,
    address: str,
) -> dict:
    """
    Simulate identity verification by checking for common mismatch patterns.

    Checks performed:
    - ID number format validity (basic format rules per id_type)
    - DOB plausibility (applicant must be 18+ and under 120)
    - Name completeness (must have at least two parts: given + family name)
    - Address completeness (must include a country or postal code indicator)
    - Nationality vs. ID type consistency (e.g. drivers_license not valid as primary
      international ID for non-resident applicants)

    Returns a dict describing confirmed status, mismatches, and follow-up questions.
    """
    mismatches: List[dict] = []
    followup_questions: List[str] = []

    # --- Name check ---
    name_parts = full_name.strip().split()
    if len(name_parts) < 2:
        mismatches.append({
            "field": "full_name",
            "stated_value": full_name,
            "expected_value": "First name and last name (at minimum)",
            "severity": "medium",
            "explanation": "Full legal name must include at least a first and last name as shown on ID.",
        })
        followup_questions.append(
            f"Could you please provide your full legal name as it appears on your {id_type}?"
        )

    # --- Date of birth plausibility ---
    try:
        dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
        today = date.today()
        age = (today - dob).days // 365
        if age < 18:
            mismatches.append({
                "field": "date_of_birth",
                "stated_value": date_of_birth,
                "expected_value": "Must be 18 years or older",
                "severity": "high",
                "explanation": "Applicant must be at least 18 years of age to open a bank account.",
            })
        elif age > 120:
            mismatches.append({
                "field": "date_of_birth",
                "stated_value": date_of_birth,
                "expected_value": "A plausible date of birth",
                "severity": "high",
                "explanation": "Date of birth indicates an implausible age. Please verify.",
            })
            followup_questions.append(
                "Could you please confirm your date of birth? The date provided appears unusual."
            )
    except ValueError:
        mismatches.append({
            "field": "date_of_birth",
            "stated_value": date_of_birth,
            "expected_value": "A valid date in YYYY-MM-DD format",
            "severity": "high",
            "explanation": "Date of birth is not in a valid format.",
        })
        followup_questions.append("Could you please provide your date of birth in YYYY-MM-DD format?")

    # --- ID number format checks ---
    id_number_clean = id_number.strip().upper().replace("-", "").replace(" ", "")
    if id_type == "passport":
        if len(id_number_clean) < 6 or len(id_number_clean) > 12:
            mismatches.append({
                "field": "id_number",
                "stated_value": id_number,
                "expected_value": "Passport number (6–12 alphanumeric characters)",
                "severity": "medium",
                "explanation": "Passport number length is outside the expected range.",
            })
            followup_questions.append(
                "Could you double-check your passport number? It appears to have an unusual length."
            )
    elif id_type == "national_id":
        if len(id_number_clean) < 5:
            mismatches.append({
                "field": "id_number",
                "stated_value": id_number,
                "expected_value": "National ID number (at least 5 characters)",
                "severity": "medium",
                "explanation": "National ID number appears too short.",
            })
    elif id_type == "drivers_license":
        if len(id_number_clean) < 5:
            mismatches.append({
                "field": "id_number",
                "stated_value": id_number,
                "expected_value": "Driver's license number (at least 5 characters)",
                "severity": "low",
                "explanation": "Driver's license number appears unusually short.",
            })

    # --- Address completeness ---
    if len(address.strip()) < 15:
        mismatches.append({
            "field": "address",
            "stated_value": address,
            "expected_value": "Full residential address including street, city, and country/postcode",
            "severity": "low",
            "explanation": "Address appears incomplete. A full address is required for KYC compliance.",
        })
        followup_questions.append(
            "Could you provide your full residential address, including street number, city, and postcode/country?"
        )

    has_high_severity = any(m["severity"] == "high" for m in mismatches)
    identity_confirmed = not has_high_severity and len(mismatches) == 0

    return {
        "status": "success",
        "full_name": full_name,
        "identity_confirmed": identity_confirmed,
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
        "requires_followup": len(mismatches) > 0,
        "followup_questions": followup_questions,
    }


def check_id_expiry(id_expiry_date: str) -> dict:
    """
    Check whether an identity document is expired or near-expiry (within 6 months).

    Args:
        id_expiry_date: Expiry date in YYYY-MM-DD format.

    Returns:
        A dict with expired, near_expiry, days_until_expiry, and a status message.
    """
    try:
        expiry = datetime.strptime(id_expiry_date, "%Y-%m-%d").date()
    except ValueError:
        return {
            "status": "error",
            "error": f"Invalid expiry date format '{id_expiry_date}'. Expected YYYY-MM-DD.",
        }

    today = date.today()
    days_until_expiry = (expiry - today).days

    expired = days_until_expiry < 0
    near_expiry = 0 <= days_until_expiry <= 180  # within 6 months

    if expired:
        message = (
            f"Identity document expired {abs(days_until_expiry)} days ago "
            f"(expiry: {id_expiry_date}). A valid, unexpired ID is required."
        )
    elif near_expiry:
        message = (
            f"Identity document expires in {days_until_expiry} days "
            f"({id_expiry_date}). Consider requesting a renewed document."
        )
    else:
        message = f"Identity document is valid for {days_until_expiry} more days."

    return {
        "status": "success",
        "id_expiry_date": id_expiry_date,
        "expired": expired,
        "near_expiry": near_expiry,
        "days_until_expiry": days_until_expiry,
        "message": message,
    }
