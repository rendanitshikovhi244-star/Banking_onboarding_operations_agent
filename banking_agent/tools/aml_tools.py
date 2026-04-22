"""
aml_tools.py
------------
Deterministic tools for AML (Anti-Money Laundering) compliance screening.

In production these would call licensed data providers:
  - PEP/Sanctions: Dow Jones Risk & Compliance, LexisNexis World-Check, Refinitiv
  - Adverse media:  ComplyAdvantage, Acuris Risk Intelligence
  - Jurisdiction:   FATF published lists (updated quarterly)

This implementation uses curated rule-based simulation to demonstrate the
screening logic without requiring third-party API keys.
"""

from __future__ import annotations

from typing import List

# ---------------------------------------------------------------------------
# Simulated screening databases (representative — not exhaustive)
# ---------------------------------------------------------------------------

# Known PEP indicators: names containing these patterns trigger PEP review.
# In production, this would be a full database query.
_PEP_NAME_PATTERNS: list[str] = [
    "minister", "senator", "governor", "ambassador", "president",
    "chairman", "general", "admiral", "secretary", "commissioner",
]

# High-risk nationalities / jurisdictions per FATF grey & black lists (April 2026 snapshot)
_FATF_HIGH_RISK_COUNTRIES: set[str] = {
    # FATF Black List (subject to enhanced countermeasures)
    "KP",  # North Korea
    "IR",  # Iran
    "MM",  # Myanmar
    # FATF Grey List (increased monitoring)
    "AF",  # Afghanistan
    "AL",  # Albania
    "BB",  # Barbados
    "BF",  # Burkina Faso
    "CM",  # Cameroon
    "CD",  # DR Congo
    "HT",  # Haiti
    "JM",  # Jamaica
    "ML",  # Mali
    "MZ",  # Mozambique
    "NG",  # Nigeria
    "PK",  # Pakistan
    "PH",  # Philippines
    "RU",  # Russia (FATF suspended)
    "SN",  # Senegal
    "ZA",  # South Africa
    "SS",  # South Sudan
    "SY",  # Syria
    "TZ",  # Tanzania
    "VE",  # Venezuela
    "YE",  # Yemen
}

# High-risk source of funds categories
_HIGH_RISK_FUNDS_SOURCES: set[str] = {
    "gambling", "casino", "cryptocurrency", "crypto", "cash",
    "remittance", "money_transfer", "hawala", "foreign_exchange",
    "forex", "precious_metals", "art_dealing", "real_estate_foreign",
}

# Simulated sanctions list entries (name fragments — production uses full-name fuzzy match)
_SANCTIONS_NAME_FRAGMENTS: set[str] = {
    "kim jong", "al-baghdadi", "bin laden", "maduro", "lukashenko",
    "khamenei", "sanctioned_person",  # test trigger
}

# Simulated adverse media triggers
_ADVERSE_MEDIA_TRIGGERS: set[str] = {
    "fraudster", "convicted", "money_laundering_suspect",  # test triggers
}


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def check_pep_status(full_name: str, nationality: str) -> dict:
    """
    Check if the applicant is a Politically Exposed Person (PEP).

    Screens the full name against known PEP name patterns. In production
    this would query a licensed PEP database with fuzzy name matching.

    Args:
        full_name: The applicant's full legal name.
        nationality: ISO 3166-1 alpha-2 country code.

    Returns:
        A dict with is_pep, confidence, pep_type, and screening_notes.
    """
    name_lower = full_name.lower()
    matched_patterns = [p for p in _PEP_NAME_PATTERNS if p in name_lower]

    is_pep = len(matched_patterns) > 0
    pep_type: str | None = None
    if is_pep:
        pep_type = "potential_PEP"

    # High-risk nationality increases PEP concern even without name match
    high_risk_nationality = nationality.upper() in _FATF_HIGH_RISK_COUNTRIES

    notes: List[str] = []
    if matched_patterns:
        notes.append(f"Name contains PEP indicator(s): {matched_patterns}")
    if high_risk_nationality:
        notes.append(f"Nationality '{nationality}' is on the FATF high-risk country list.")

    return {
        "status": "success",
        "full_name": full_name,
        "nationality": nationality,
        "is_pep": is_pep,
        "pep_type": pep_type,
        "high_risk_nationality": high_risk_nationality,
        "screening_notes": notes,
        "data_source": "simulated_pep_database_v2026",
    }


def check_sanctions_list(
    full_name: str,
    nationality: str,
    date_of_birth: str,
) -> dict:
    """
    Check the applicant against OFAC, EU, and UN consolidated sanctions lists.

    Args:
        full_name: The applicant's full legal name.
        nationality: ISO 3166-1 alpha-2 country code.
        date_of_birth: DOB in YYYY-MM-DD format.

    Returns:
        A dict with sanctions_hit, matched_lists, matched_entry, and match_score.
    """
    name_lower = full_name.lower()
    matched_lists: List[str] = []
    matched_entry: str | None = None

    for fragment in _SANCTIONS_NAME_FRAGMENTS:
        if fragment in name_lower:
            matched_lists = ["OFAC SDN", "EU Consolidated", "UN Security Council"]
            matched_entry = fragment.title()
            break

    # Country-level sanctions: some nationalities trigger list-level screening
    country_sanctioned = nationality.upper() in {"KP", "IR", "SY", "CU"}
    if country_sanctioned and not matched_lists:
        matched_lists = ["OFAC Country-Level Restriction"]
        matched_entry = f"Country restriction: {nationality}"

    sanctions_hit = len(matched_lists) > 0
    match_score = 0.95 if sanctions_hit else 0.0

    return {
        "status": "success",
        "full_name": full_name,
        "nationality": nationality,
        "date_of_birth": date_of_birth,
        "sanctions_hit": sanctions_hit,
        "matched_lists": matched_lists,
        "matched_entry": matched_entry,
        "match_score": match_score,
        "data_source": "simulated_sanctions_db_v2026",
    }


def check_adverse_media(full_name: str, nationality: str) -> dict:
    """
    Check for adverse media coverage linking the applicant to financial crime.

    Screens for news articles, regulatory actions, or legal proceedings related
    to money laundering, fraud, corruption, or terrorism financing.

    Args:
        full_name: The applicant's full legal name.
        nationality: ISO 3166-1 alpha-2 country code.

    Returns:
        A dict with adverse_media_hit, article_count, categories, and summary.
    """
    name_lower = full_name.lower()
    categories: List[str] = []

    for trigger in _ADVERSE_MEDIA_TRIGGERS:
        if trigger.replace("_", " ") in name_lower or trigger in name_lower:
            categories = ["financial_crime", "fraud"]
            break

    adverse_media_hit = len(categories) > 0
    article_count = 3 if adverse_media_hit else 0

    return {
        "status": "success",
        "full_name": full_name,
        "nationality": nationality,
        "adverse_media_hit": adverse_media_hit,
        "article_count": article_count,
        "categories": categories,
        "summary": (
            f"Found {article_count} adverse media article(s) in categories: {categories}"
            if adverse_media_hit
            else "No adverse media found."
        ),
        "data_source": "simulated_adverse_media_db_v2026",
    }


def screen_high_risk_jurisdiction(
    country_of_residence: str,
    nationality: str,
) -> dict:
    """
    Check whether the applicant's country of residence or nationality is on the
    FATF high-risk and other monitored jurisdictions list.

    Args:
        country_of_residence: ISO 3166-1 alpha-2 country code of residence.
        nationality: ISO 3166-1 alpha-2 country code of nationality.

    Returns:
        A dict with is_high_risk, risk_level, flagged_countries, and fatf_status.
    """
    residence_upper = country_of_residence.upper().strip()
    nationality_upper = nationality.upper().strip()

    flagged: List[dict] = []

    if residence_upper in _FATF_HIGH_RISK_COUNTRIES:
        fatf_status = "black_list" if residence_upper in {"KP", "IR", "MM"} else "grey_list"
        flagged.append({
            "country": residence_upper,
            "reason": "country_of_residence",
            "fatf_status": fatf_status,
        })

    if nationality_upper in _FATF_HIGH_RISK_COUNTRIES and nationality_upper != residence_upper:
        fatf_status = "black_list" if nationality_upper in {"KP", "IR", "MM"} else "grey_list"
        flagged.append({
            "country": nationality_upper,
            "reason": "nationality",
            "fatf_status": fatf_status,
        })

    is_high_risk = len(flagged) > 0
    has_blacklisted = any(f["fatf_status"] == "black_list" for f in flagged)
    risk_level = "critical" if has_blacklisted else ("high" if is_high_risk else "standard")

    return {
        "status": "success",
        "country_of_residence": country_of_residence,
        "nationality": nationality,
        "is_high_risk": is_high_risk,
        "risk_level": risk_level,
        "flagged_countries": flagged,
        "data_source": "FATF_list_April_2026",
    }
