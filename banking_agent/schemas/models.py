from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class CustomerIntake(BaseModel):
    """Normalised customer application record produced by IntakeAgent."""

    application_id: str = Field(description="Unique application identifier, e.g. APP-20260422-001")
    full_name: str
    date_of_birth: str = Field(description="YYYY-MM-DD")
    nationality: str = Field(description="ISO 3166-1 alpha-2 country code, e.g. US")
    country_of_residence: str = Field(description="ISO 3166-1 alpha-2 country code")
    id_type: Literal["passport", "national_id", "drivers_license"]
    id_number: str
    id_expiry_date: str = Field(description="YYYY-MM-DD")
    address: str
    phone_number: str
    email: str
    account_type: Literal[
        "personal_checking",
        "personal_savings",
        "business_current",
        "business_savings",
        "investment",
    ]
    source_of_funds: str
    employment_status: Literal[
        "employed", "self_employed", "retired", "student", "unemployed", "business_owner"
    ]
    annual_income: float = Field(ge=0)
    documents_provided: List[str] = Field(default_factory=list)


class DocumentCheckResult(BaseModel):
    """KYC document completeness check produced by DocumentAgent."""

    application_id: str
    account_type: str
    required_docs: List[str]
    provided_docs: List[str]
    missing_docs: List[str]
    all_docs_present: bool
    followup_request: Optional[str] = Field(
        default=None,
        description="Polite request message listing missing documents",
    )


class IdentityMismatch(BaseModel):
    """A single detected mismatch between stated identity and document evidence."""

    field: str = Field(description="The identity field where the mismatch was found")
    stated_value: str = Field(description="What the applicant stated")
    expected_value: str = Field(description="What the documents indicate")
    severity: Literal["low", "medium", "high"]
    explanation: str


class IdentityVerification(BaseModel):
    """Identity cross-check result produced by IdentityAgent."""

    application_id: str
    id_expired: bool
    id_near_expiry: bool = Field(description="True if ID expires within 6 months")
    identity_confirmed: bool = Field(description="True when no high-severity mismatches found")
    mismatches: List[IdentityMismatch] = Field(default_factory=list)
    mismatch_count: int
    requires_followup: bool
    followup_questions: List[str] = Field(default_factory=list)


class AMLScreeningResult(BaseModel):
    """AML screening result produced by AMLAgent."""

    application_id: str
    is_pep: bool = Field(description="Politically Exposed Person indicator")
    sanctions_hit: bool = Field(description="Match found on OFAC, EU, or UN sanctions lists")
    adverse_media_hit: bool
    high_risk_jurisdiction: bool
    aml_risk_score: float = Field(ge=0.0, le=1.0)
    risk_factors: List[str] = Field(default_factory=list)
    screening_flags: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """Composite customer risk assessment produced by RiskAgent."""

    application_id: str
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high", "critical"]
    routing_decision: Literal[
        "auto_approve",
        "standard_review",
        "enhanced_due_diligence",
        "compliance_escalation",
        "reject",
    ]
    risk_factors: List[str] = Field(default_factory=list)
    compliance_notes: str


class AuditEntry(BaseModel):
    """A single audit trail entry appended to Redis by any pipeline agent."""

    application_id: str
    agent_name: str
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )
    decision: str
    details: dict = Field(default_factory=dict)


class OnboardingDecision(BaseModel):
    """Final onboarding decision compiled by AuditAgent."""

    application_id: str
    overall_status: Literal[
        "approved",
        "pending_documents",
        "pending_review",
        "compliance_escalated",
        "rejected",
    ]
    risk_level: str
    account_type: str
    missing_docs: List[str] = Field(default_factory=list)
    identity_mismatches: List[str] = Field(
        default_factory=list,
        description="Human-readable mismatch descriptions",
    )
    aml_flags: List[str] = Field(default_factory=list)
    compliance_notes: str
    next_steps: List[str] = Field(
        default_factory=list,
        description="Ordered list of required actions for the customer or bank",
    )
    summary: str
    audit_key: str
