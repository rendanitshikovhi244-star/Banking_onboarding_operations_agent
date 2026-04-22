"""
pipeline_runner_tool.py
-----------------------
Tools used by OnboardingAssistant to trigger the KYC pipeline.

  submit_application            — first submission, runs the full KYC pipeline
  resubmit_with_documents       — resubmit after customer provides missing documents
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date
from pathlib import Path

import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
logger = logging.getLogger("banking_agent.pipeline")


def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(_REDIS_URL, decode_responses=True)


def _format_result(state: dict) -> str:
    """Format the pipeline final_decision for display to the customer."""
    final = state.get("final_decision")
    if not final:
        return "The onboarding pipeline did not produce a result. Please try again."
    try:
        data = json.loads(final) if isinstance(final, str) else final
        status = data.get("overall_status", "unknown").upper().replace("_", " ")
        risk = data.get("risk_level", "N/A").upper()

        lines = [
            f"Application ID  : {data.get('application_id', 'N/A')}",
            f"Status          : {status}",
            f"Risk Level      : {risk}",
            f"Account Type    : {data.get('account_type', 'N/A')}",
        ]

        missing = data.get("missing_docs", [])
        if missing:
            lines.append(f"Missing Docs    : {', '.join(missing)}")

        mismatches = data.get("identity_mismatches", [])
        if mismatches:
            lines.append("ID Mismatches   : " + "; ".join(mismatches))

        aml_flags = data.get("aml_flags", [])
        if aml_flags:
            lines.append("AML Flags       : " + "; ".join(aml_flags))

        next_steps = data.get("next_steps", [])
        if next_steps:
            lines.append("Next Steps      :")
            for step in next_steps:
                lines.append(f"  • {step}")

        lines.append(f"\nSummary: {data.get('summary', '')}")
        return "\n".join(lines)
    except Exception:  # noqa: BLE001
        return f"Pipeline completed. Raw result: {final}"


async def _run_pipeline_internal(application_json: str) -> dict:
    """Run the KYC pipeline internally. Uses lazy import to avoid circular deps."""
    from banking_agent.agent import banking_onboarding_agent  # lazy import
    session_id = f"internal_{uuid.uuid4().hex[:12]}"
    return await banking_onboarding_agent.process_application(
        application_input=application_json,
        session_id=session_id,
        user_id="onboarding_assistant",
    )


async def submit_application(
    full_name: str,
    date_of_birth: str,
    nationality: str,
    country_of_residence: str,
    id_type: str,
    id_number: str,
    id_expiry_date: str,
    address: str,
    phone_number: str,
    email: str,
    account_type: str,
    source_of_funds: str,
    employment_status: str,
    annual_income: float,
    documents_provided: str = "",
) -> str:
    """
    Submit a customer application through the full KYC onboarding pipeline.

    This tool is called by OnboardingAssistant after collecting all required
    customer information in the conversation.

    Args:
        full_name: Customer's full legal name.
        date_of_birth: Date of birth in YYYY-MM-DD format.
        nationality: ISO 3166-1 alpha-2 country code.
        country_of_residence: ISO 3166-1 alpha-2 country code.
        id_type: One of: passport, national_id, drivers_license.
        id_number: Identity document number.
        id_expiry_date: Document expiry date in YYYY-MM-DD format.
        address: Full residential address.
        phone_number: Contact phone number with country code.
        email: Email address.
        account_type: One of: personal_checking, personal_savings, business_current,
                     business_savings, investment.
        source_of_funds: Description of income/fund source.
        employment_status: One of: employed, self_employed, retired, student,
                          unemployed, business_owner.
        annual_income: Annual income in local currency.
        documents_provided: Comma-separated list of submitted document names.

    Returns:
        Formatted string with APPLICATION_ID prefix and the pipeline result summary.
    """
    today = date.today().strftime("%Y%m%d")
    application_id = f"APP-{today}-{uuid.uuid4().hex[:4].upper()}"

    docs = (
        [d.strip() for d in documents_provided.split(",") if d.strip()]
        if documents_provided
        else []
    )

    application_data = {
        "application_id": application_id,
        "full_name": full_name,
        "date_of_birth": date_of_birth,
        "nationality": nationality,
        "country_of_residence": country_of_residence,
        "id_type": id_type,
        "id_number": id_number,
        "id_expiry_date": id_expiry_date,
        "address": address,
        "phone_number": phone_number,
        "email": email,
        "account_type": account_type,
        "source_of_funds": source_of_funds,
        "employment_status": employment_status,
        "annual_income": float(annual_income),
        "documents_provided": docs,
    }

    # Persist raw application data to Redis for resubmission
    r = _get_redis()
    try:
        await r.set(
            f"application_data:{application_id}",
            json.dumps(application_data),
            ex=86400,
        )
    finally:
        await r.aclose()

    state = await _run_pipeline_internal(json.dumps(application_data))
    return f"APPLICATION_ID:{application_id}\n" + _format_result(state)


async def resubmit_with_documents(
    application_id: str,
    new_documents: str,
) -> str:
    """
    Resubmit an application with additional documents to clear a pending_documents status.

    Retrieves the original application data from Redis, merges the new documents
    with any previously submitted ones, and re-runs the full KYC pipeline.

    Args:
        application_id: The application ID from the original submission.
        new_documents: Comma-separated list of newly provided document names.

    Returns:
        Formatted string with APPLICATION_ID prefix and the updated pipeline result.
    """
    r = _get_redis()
    try:
        raw = await r.get(f"application_data:{application_id}")
        if not raw:
            return (
                f"No application data found for {application_id}. "
                "The data may have expired (24-hour limit) or the ID is incorrect."
            )
        application_data = json.loads(raw)

        existing: set[str] = set(application_data.get("documents_provided", []))
        new_docs: set[str] = {d.strip() for d in new_documents.split(",") if d.strip()}
        application_data["documents_provided"] = sorted(existing | new_docs)

        await r.set(
            f"application_data:{application_id}",
            json.dumps(application_data),
            ex=86400,
        )
    finally:
        await r.aclose()

    state = await _run_pipeline_internal(json.dumps(application_data))
    return f"APPLICATION_ID:{application_id}\n" + _format_result(state)
