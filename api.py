"""
api.py
------
FastAPI interface for the Banking Onboarding / KYC Multi-Agent System.

Endpoints:
  GET  /health                          — liveness + Redis connectivity check
  POST /applications                    — submit a customer application through the KYC pipeline
  GET  /applications/{application_id}/audit  — fetch the ordered audit trail from Redis
  GET  /compliance-queue                — inspect the compliance escalation queue

Run with:
    uvicorn api:app --reload
    uvicorn api:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, List, Literal, Optional

import redis.asyncio as aioredis
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).parent / "banking_agent" / ".env")

from banking_agent.configs.logging_config import configure as _configure_logging

_configure_logging()

from banking_agent.agent import banking_onboarding_agent  # noqa: E402


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Banking Onboarding / KYC API",
    description=(
        "Customer onboarding and KYC pipeline powered by a Google ADK "
        "multi-agent system. Submit a customer application and receive an "
        "immediate onboarding decision covering document validation, identity "
        "verification, AML screening, and risk assessment."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

_REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _redis() -> aioredis.Redis:
    return aioredis.from_url(_REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ApplicationRequest(BaseModel):
    """
    Structured customer application submission.

    Either provide structured fields *or* a `raw_input` string (JSON or
    free-text). When `raw_input` is present all other fields are ignored.
    """

    full_name: Optional[str] = Field(default=None, examples=["Jane Smith"])
    date_of_birth: Optional[str] = Field(
        default=None,
        description="Date of birth in YYYY-MM-DD format",
        examples=["1985-06-15"],
    )
    nationality: Optional[str] = Field(default=None, examples=["US"])
    country_of_residence: Optional[str] = Field(default=None, examples=["US"])
    id_type: Optional[Literal["passport", "national_id", "drivers_license"]] = None
    id_number: Optional[str] = Field(default=None, examples=["P12345678"])
    id_expiry_date: Optional[str] = Field(default=None, examples=["2030-01-01"])
    address: Optional[str] = Field(default=None, examples=["123 Main St, New York, NY 10001"])
    phone_number: Optional[str] = Field(default=None, examples=["+1-212-555-0100"])
    email: Optional[str] = Field(default=None, examples=["jane.smith@email.com"])
    account_type: Optional[
        Literal[
            "personal_checking",
            "personal_savings",
            "business_current",
            "business_savings",
            "investment",
        ]
    ] = None
    source_of_funds: Optional[str] = Field(default=None, examples=["employment"])
    employment_status: Optional[
        Literal["employed", "self_employed", "retired", "student", "unemployed", "business_owner"]
    ] = None
    annual_income: Optional[float] = Field(default=None, ge=0, examples=[65000.0])
    documents_provided: List[str] = Field(
        default_factory=list,
        description="Document names already submitted with the application.",
        examples=[["government_id", "proof_of_address"]],
    )
    raw_input: Optional[str] = Field(
        default=None,
        description=(
            "Free-text or raw JSON application input. "
            "When provided, all other fields are ignored."
        ),
    )


class OnboardingResponse(BaseModel):
    application_id: str
    session_id: str
    overall_status: str
    risk_level: Optional[str] = None
    account_type: Optional[str] = None
    missing_docs: List[str] = []
    identity_mismatches: List[str] = []
    aml_flags: List[str] = []
    next_steps: List[str] = []
    compliance_notes: Optional[str] = None
    summary: Optional[str] = None


class AuditEntryOut(BaseModel):
    application_id: str
    agent_name: str
    timestamp: str
    decision: str
    details: Any


class AuditLogResponse(BaseModel):
    application_id: str
    entry_count: int
    entries: List[AuditEntryOut]


class ComplianceQueueResponse(BaseModel):
    queue_length: int
    application_ids: List[str]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    redis: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _new_application_id() -> str:
    today = date.today().strftime("%Y%m%d")
    return f"APP-{today}-{uuid.uuid4().hex[:4].upper()}"


def _build_application_payload(req: ApplicationRequest) -> tuple[str, str]:
    """Return ``(application_id, application_json)`` ready to pass to process_application."""
    if req.raw_input:
        try:
            parsed = json.loads(req.raw_input)
            application_id = parsed.get("application_id") or _new_application_id()
        except (json.JSONDecodeError, AttributeError):
            application_id = _new_application_id()
        return application_id, req.raw_input

    application_id = _new_application_id()
    payload = {
        "application_id": application_id,
        "full_name": req.full_name or "",
        "date_of_birth": req.date_of_birth or "",
        "nationality": req.nationality or "US",
        "country_of_residence": req.country_of_residence or "US",
        "id_type": req.id_type or "passport",
        "id_number": req.id_number or "",
        "id_expiry_date": req.id_expiry_date or "",
        "address": req.address or "",
        "phone_number": req.phone_number or "",
        "email": req.email or "",
        "account_type": req.account_type or "personal_checking",
        "source_of_funds": req.source_of_funds or "",
        "employment_status": req.employment_status or "employed",
        "annual_income": req.annual_income or 0.0,
        "documents_provided": req.documents_provided,
    }
    return application_id, json.dumps(payload)


def _parse_onboarding_response(state: dict, session_id: str) -> OnboardingResponse:
    """Extract the final_decision from the pipeline session state."""
    final = state.get("final_decision")
    if not final:
        raise HTTPException(
            status_code=500,
            detail="Pipeline completed but did not produce a final_decision.",
        )
    try:
        data = json.loads(final) if isinstance(final, str) else final
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(
            status_code=500, detail=f"Could not parse pipeline result: {exc}"
        ) from exc

    return OnboardingResponse(
        application_id=data.get("application_id", "unknown"),
        session_id=session_id,
        overall_status=data.get("overall_status", "unknown"),
        risk_level=data.get("risk_level"),
        account_type=data.get("account_type"),
        missing_docs=data.get("missing_docs", []),
        identity_mismatches=data.get("identity_mismatches", []),
        aml_flags=data.get("aml_flags", []),
        next_steps=data.get("next_steps", []),
        compliance_notes=data.get("compliance_notes"),
        summary=data.get("summary"),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["Operations"])
async def health_check() -> HealthResponse:
    """Check that the API is up and Redis is reachable."""
    redis_status = "ok"
    try:
        r = _redis()
        await r.ping()
        await r.aclose()
    except Exception as exc:  # noqa: BLE001
        redis_status = f"error: {exc}"

    overall: Literal["ok", "degraded"] = "ok" if redis_status == "ok" else "degraded"
    return HealthResponse(status=overall, redis=redis_status)


@app.post(
    "/applications",
    response_model=OnboardingResponse,
    status_code=202,
    tags=["Onboarding"],
)
async def submit_application(req: ApplicationRequest) -> OnboardingResponse:
    """
    Submit a customer application through the full KYC onboarding pipeline.

    Accepts structured fields or a `raw_input` string (JSON or free-text).
    Runs the complete 5-stage pipeline (intake → document check →
    identity verification + AML screening → risk assessment → audit decision)
    and returns the onboarding decision synchronously.
    """
    application_id, application_json = _build_application_payload(req)
    session_id = f"api_{uuid.uuid4().hex[:12]}"

    try:
        state = await banking_onboarding_agent.process_application(
            application_input=application_json,
            session_id=session_id,
            user_id="api",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _parse_onboarding_response(state, session_id)


@app.get(
    "/applications/{application_id}/audit",
    response_model=AuditLogResponse,
    tags=["Onboarding"],
)
async def get_audit_log(application_id: str) -> AuditLogResponse:
    """Fetch the ordered audit trail for an application from Redis."""
    r = _redis()
    try:
        raw_entries = await r.lrange(f"audit:{application_id}", 0, -1)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Redis error: {exc}") from exc
    finally:
        await r.aclose()

    if not raw_entries:
        raise HTTPException(
            status_code=404,
            detail=f"No audit log found for application '{application_id}'.",
        )

    entries: list[AuditEntryOut] = []
    for raw in raw_entries:
        try:
            entry_data = json.loads(raw)
            details = entry_data.get("details", {})
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except (json.JSONDecodeError, TypeError):
                    pass
            entries.append(
                AuditEntryOut(
                    application_id=entry_data.get("application_id", application_id),
                    agent_name=entry_data.get("agent_name", "unknown"),
                    timestamp=entry_data.get("timestamp", ""),
                    decision=entry_data.get("decision", ""),
                    details=details,
                )
            )
        except (json.JSONDecodeError, Exception):  # noqa: BLE001
            continue

    return AuditLogResponse(
        application_id=application_id,
        entry_count=len(entries),
        entries=entries,
    )


@app.get(
    "/compliance-queue",
    response_model=ComplianceQueueResponse,
    tags=["Operations"],
)
async def get_compliance_queue() -> ComplianceQueueResponse:
    """Inspect all application IDs currently in the compliance escalation queue."""
    r = _redis()
    try:
        items = await r.lrange("compliance_review_queue", 0, -1)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Redis error: {exc}") from exc
    finally:
        await r.aclose()

    parsed_ids: list[str] = []
    for item in items:
        try:
            payload = json.loads(item)
            parsed_ids.append(payload.get("application_id", item))
        except (json.JSONDecodeError, TypeError):
            parsed_ids.append(item)

    return ComplianceQueueResponse(queue_length=len(items), application_ids=parsed_ids)
