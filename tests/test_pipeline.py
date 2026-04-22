"""
test_pipeline.py
----------------
Unit and integration tests for the Banking Onboarding / KYC multi-agent system.

Tests cover:
  - Pydantic schema validation
  - Document tool logic (get_required_kyc_documents, check_kyc_documents)
  - Identity tool logic (verify_identity, check_id_expiry)
  - AML tool logic (check_pep_status, check_sanctions_list, screen_high_risk_jurisdiction)
  - Redis tools with mocked Redis (no live Redis required)
  - End-to-end pipeline with mocked LLM responses
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from banking_agent.schemas.models import (
    AuditEntry,
    CustomerIntake,
    DocumentCheckResult,
    IdentityVerification,
    AMLScreeningResult,
    RiskAssessment,
    OnboardingDecision,
)
from banking_agent.tools.document_tools import (
    get_required_kyc_documents,
    check_kyc_documents,
)
from banking_agent.tools.identity_tools import verify_identity, check_id_expiry
from banking_agent.tools.aml_tools import (
    check_pep_status,
    check_sanctions_list,
    check_adverse_media,
    screen_high_risk_jurisdiction,
)


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_customer_intake_valid(self):
        intake = CustomerIntake(
            application_id="APP-20260422-001",
            full_name="Sarah Johnson",
            date_of_birth="1988-03-15",
            nationality="US",
            country_of_residence="US",
            id_type="passport",
            id_number="P12345678",
            id_expiry_date="2030-03-15",
            address="123 Oak Street, New York, NY 10001, USA",
            phone_number="+1-212-555-0100",
            email="sarah@email.com",
            account_type="personal_checking",
            source_of_funds="employment",
            employment_status="employed",
            annual_income=75000.0,
            documents_provided=["government_id", "proof_of_address"],
        )
        assert intake.application_id == "APP-20260422-001"
        assert intake.account_type == "personal_checking"

    def test_customer_intake_invalid_account_type(self):
        with pytest.raises(Exception):
            CustomerIntake(
                application_id="APP-001",
                full_name="Test User",
                date_of_birth="1990-01-01",
                nationality="US",
                country_of_residence="US",
                id_type="passport",
                id_number="P99999999",
                id_expiry_date="2030-01-01",
                address="123 Test St",
                phone_number="+1-555-0000",
                email="test@test.com",
                account_type="crypto_wallet",  # invalid
                source_of_funds="employment",
                employment_status="employed",
                annual_income=50000.0,
            )

    def test_risk_assessment_score_bounds(self):
        assessment = RiskAssessment(
            application_id="APP-001",
            risk_score=0.75,
            risk_level="critical",
            routing_decision="compliance_escalation",
            risk_factors=["pep_hit", "high_risk_jurisdiction"],
            compliance_notes="Escalated due to PEP status and high-risk jurisdiction.",
        )
        assert 0.0 <= assessment.risk_score <= 1.0
        assert assessment.routing_decision == "compliance_escalation"

    def test_onboarding_decision_valid(self):
        decision = OnboardingDecision(
            application_id="APP-001",
            overall_status="approved",
            risk_level="low",
            account_type="personal_savings",
            missing_docs=[],
            identity_mismatches=[],
            aml_flags=[],
            compliance_notes="Standard low-risk individual account.",
            next_steps=["Account will be created within 1-2 business days."],
            summary="Application approved. All KYC checks passed.",
            audit_key="audit:APP-001",
        )
        assert decision.overall_status == "approved"
        assert decision.audit_key == "audit:APP-001"

    def test_aml_screening_result_bounds(self):
        result = AMLScreeningResult(
            application_id="APP-001",
            is_pep=False,
            sanctions_hit=False,
            adverse_media_hit=False,
            high_risk_jurisdiction=False,
            aml_risk_score=0.0,
            risk_factors=[],
            screening_flags=[],
        )
        assert 0.0 <= result.aml_risk_score <= 1.0


# ---------------------------------------------------------------------------
# Document tool tests
# ---------------------------------------------------------------------------


class TestDocumentTools:
    def test_get_required_docs_personal_checking(self):
        result = get_required_kyc_documents("personal_checking")
        assert result["status"] == "success"
        assert "government_id" in result["required_documents"]
        assert "proof_of_address" in result["required_documents"]
        assert "proof_of_income" in result["required_documents"]

    def test_get_required_docs_investment(self):
        result = get_required_kyc_documents("investment")
        assert result["status"] == "success"
        assert "source_of_funds_declaration" in result["required_documents"]
        assert "tax_identification_number" in result["required_documents"]

    def test_get_required_docs_business_current(self):
        result = get_required_kyc_documents("business_current")
        assert result["status"] == "success"
        assert "ubo_declaration" in result["required_documents"]
        assert "bank_statements_6months" in result["required_documents"]

    def test_get_required_docs_unknown_type(self):
        result = get_required_kyc_documents("crypto_wallet")
        assert result["status"] == "error"
        assert "Unknown account type" in result["error"]

    def test_check_kyc_docs_all_present(self):
        result = check_kyc_documents(
            "personal_savings",
            json.dumps(["government_id", "proof_of_address"]),
        )
        assert result["status"] == "success"
        assert result["all_present"] is True
        assert result["missing_documents"] == []

    def test_check_kyc_docs_missing_docs(self):
        result = check_kyc_documents(
            "personal_checking",
            json.dumps(["government_id"]),
        )
        assert result["status"] == "success"
        assert result["all_present"] is False
        assert "proof_of_address" in result["missing_documents"]
        assert "proof_of_income" in result["missing_documents"]
        assert result["followup_request"] is not None

    def test_check_kyc_docs_comma_separated_input(self):
        result = check_kyc_documents(
            "personal_savings",
            "government_id, proof_of_address",
        )
        assert result["status"] == "success"
        assert result["all_present"] is True

    def test_check_kyc_docs_business_missing_ubo(self):
        result = check_kyc_documents(
            "business_current",
            json.dumps(["company_registration", "certificate_of_incorporation"]),
        )
        assert result["status"] == "success"
        assert "ubo_declaration" in result["missing_documents"]
        assert "director_ids" in result["missing_documents"]


# ---------------------------------------------------------------------------
# Identity tool tests
# ---------------------------------------------------------------------------


class TestIdentityTools:
    def test_verify_identity_valid(self):
        result = verify_identity(
            full_name="Sarah Johnson",
            date_of_birth="1988-03-15",
            id_type="passport",
            id_number="P12345678",
            id_expiry_date="2030-03-15",
            nationality="US",
            address="123 Oak Street, New York, NY 10001, USA",
        )
        assert result["status"] == "success"
        assert result["mismatch_count"] == 0

    def test_verify_identity_underage(self):
        result = verify_identity(
            full_name="Young Person",
            date_of_birth="2015-01-01",  # under 18
            id_type="passport",
            id_number="P11111111",
            id_expiry_date="2030-01-01",
            nationality="US",
            address="123 Main St, New York, NY 10001, USA",
        )
        assert result["status"] == "success"
        assert result["mismatch_count"] > 0
        age_mismatch = next(
            (m for m in result["mismatches"] if m["field"] == "date_of_birth"), None
        )
        assert age_mismatch is not None
        assert age_mismatch["severity"] == "high"

    def test_verify_identity_single_name(self):
        result = verify_identity(
            full_name="Madonna",  # single name
            date_of_birth="1958-08-16",
            id_type="passport",
            id_number="P22222222",
            id_expiry_date="2030-01-01",
            nationality="US",
            address="123 Main St, New York, NY 10001, USA",
        )
        assert result["status"] == "success"
        name_mismatch = next(
            (m for m in result["mismatches"] if m["field"] == "full_name"), None
        )
        assert name_mismatch is not None

    def test_check_id_expiry_valid(self):
        result = check_id_expiry("2030-01-01")
        assert result["status"] == "success"
        assert result["expired"] is False
        assert result["near_expiry"] is False
        assert result["days_until_expiry"] > 180

    def test_check_id_expiry_expired(self):
        result = check_id_expiry("2020-01-01")
        assert result["status"] == "success"
        assert result["expired"] is True
        assert result["days_until_expiry"] < 0

    def test_check_id_expiry_near_expiry(self):
        from datetime import date, timedelta
        near_date = (date.today() + timedelta(days=90)).strftime("%Y-%m-%d")
        result = check_id_expiry(near_date)
        assert result["status"] == "success"
        assert result["near_expiry"] is True
        assert result["expired"] is False

    def test_check_id_expiry_invalid_format(self):
        result = check_id_expiry("01/01/2030")
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# AML tool tests
# ---------------------------------------------------------------------------


class TestAMLTools:
    def test_pep_check_clean(self):
        result = check_pep_status("Sarah Johnson", "US")
        assert result["status"] == "success"
        assert result["is_pep"] is False

    def test_pep_check_name_match(self):
        result = check_pep_status("John Minister Smith", "GB")
        assert result["status"] == "success"
        assert result["is_pep"] is True

    def test_pep_check_high_risk_nationality(self):
        result = check_pep_status("Ivan Petrov", "RU")
        assert result["status"] == "success"
        assert result["high_risk_nationality"] is True

    def test_sanctions_check_clean(self):
        result = check_sanctions_list("Sarah Johnson", "US", "1988-03-15")
        assert result["status"] == "success"
        assert result["sanctions_hit"] is False

    def test_sanctions_check_country_restriction(self):
        result = check_sanctions_list("Ali Hassan", "IR", "1970-01-01")
        assert result["status"] == "success"
        assert result["sanctions_hit"] is True
        assert len(result["matched_lists"]) > 0

    def test_adverse_media_clean(self):
        result = check_adverse_media("Sarah Johnson", "US")
        assert result["status"] == "success"
        assert result["adverse_media_hit"] is False

    def test_screen_jurisdiction_standard(self):
        result = screen_high_risk_jurisdiction("US", "US")
        assert result["status"] == "success"
        assert result["is_high_risk"] is False
        assert result["risk_level"] == "standard"

    def test_screen_jurisdiction_high_risk_residence(self):
        result = screen_high_risk_jurisdiction("NG", "US")
        assert result["status"] == "success"
        assert result["is_high_risk"] is True

    def test_screen_jurisdiction_blacklisted_nationality(self):
        result = screen_high_risk_jurisdiction("AE", "KP")
        assert result["status"] == "success"
        assert result["is_high_risk"] is True
        assert any(f["fatf_status"] == "black_list" for f in result["flagged_countries"])

    def test_screen_jurisdiction_both_flagged(self):
        result = screen_high_risk_jurisdiction("RU", "RU")
        assert result["status"] == "success"
        assert result["is_high_risk"] is True
        # Should only appear once (same country)
        assert len(result["flagged_countries"]) == 1


# ---------------------------------------------------------------------------
# Redis tools tests (mocked)
# ---------------------------------------------------------------------------


class TestRedisTools:
    @pytest.mark.asyncio
    async def test_write_audit_log_success(self):
        with patch("banking_agent.tools.redis_tools._get_redis") as mock_get:
            mock_redis = AsyncMock()
            mock_redis.rpush = AsyncMock(return_value=1)
            mock_redis.aclose = AsyncMock()
            mock_get.return_value = mock_redis

            from banking_agent.tools.redis_tools import write_audit_log

            result = await write_audit_log(
                application_id="APP-001",
                agent_name="DocumentAgent",
                decision="docs_incomplete",
                details='{"missing": ["proof_of_income"]}',
            )
            assert result["status"] == "success"
            assert "audit:APP-001" in result["redis_key"]
            mock_redis.rpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_compliance_queue_success(self):
        with patch("banking_agent.tools.redis_tools._get_redis") as mock_get:
            mock_redis = AsyncMock()
            mock_redis.rpush = AsyncMock(return_value=1)
            mock_redis.aclose = AsyncMock()
            mock_get.return_value = mock_redis

            from banking_agent.tools.redis_tools import push_compliance_queue

            result = await push_compliance_queue(
                application_id="APP-003",
                risk_score=0.85,
                risk_level="critical",
                risk_factors='["pep_hit", "high_risk_jurisdiction", "expired_id"]',
            )
            assert result["status"] == "success"
            assert result["queue"] == "compliance_review_queue"

    @pytest.mark.asyncio
    async def test_write_audit_log_redis_error(self):
        with patch("banking_agent.tools.redis_tools._get_redis") as mock_get:
            mock_redis = AsyncMock()
            mock_redis.rpush = AsyncMock(side_effect=ConnectionError("Redis unavailable"))
            mock_redis.aclose = AsyncMock()
            mock_get.return_value = mock_redis

            from banking_agent.tools.redis_tools import write_audit_log

            result = await write_audit_log(
                application_id="APP-001",
                agent_name="DocumentAgent",
                decision="error",
                details="{}",
            )
            assert result["status"] == "error"
            assert "Redis unavailable" in result["error"]


# ---------------------------------------------------------------------------
# End-to-end pipeline test (mocked LLM)
# ---------------------------------------------------------------------------


class TestPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_runs_all_stages(self):
        """Verify the pipeline calls all 5 agents in correct order."""
        from banking_agent.agent import BankingOnboardingAgent
        from banking_agent.sessions import RedisSessionService

        intake_response = json.dumps({
            "application_id": "APP-20260422-001",
            "full_name": "Sarah Johnson",
            "date_of_birth": "1988-03-15",
            "nationality": "US",
            "country_of_residence": "US",
            "id_type": "passport",
            "id_number": "P12345678",
            "id_expiry_date": "2030-03-15",
            "address": "123 Oak Street, New York, NY 10001, USA",
            "phone_number": "+1-212-555-0100",
            "email": "sarah@email.com",
            "account_type": "personal_checking",
            "source_of_funds": "employment",
            "employment_status": "employed",
            "annual_income": 75000.0,
            "documents_provided": ["government_id", "proof_of_address", "proof_of_income"],
        })

        doc_response = json.dumps({
            "application_id": "APP-20260422-001",
            "account_type": "personal_checking",
            "required_docs": ["government_id", "proof_of_address", "proof_of_income"],
            "provided_docs": ["government_id", "proof_of_address", "proof_of_income"],
            "missing_docs": [],
            "all_docs_present": True,
        })

        identity_response = json.dumps({
            "application_id": "APP-20260422-001",
            "id_expired": False,
            "id_near_expiry": False,
            "identity_confirmed": True,
            "mismatches": [],
            "mismatch_count": 0,
            "requires_followup": False,
            "followup_questions": [],
        })

        aml_response = json.dumps({
            "application_id": "APP-20260422-001",
            "is_pep": False,
            "sanctions_hit": False,
            "adverse_media_hit": False,
            "high_risk_jurisdiction": False,
            "aml_risk_score": 0.0,
            "risk_factors": [],
            "screening_flags": [],
        })

        risk_response = json.dumps({
            "application_id": "APP-20260422-001",
            "risk_score": 0.05,
            "risk_level": "low",
            "routing_decision": "auto_approve",
            "risk_factors": [],
            "compliance_notes": "Standard low-risk individual application.",
        })

        final_response = json.dumps({
            "application_id": "APP-20260422-001",
            "overall_status": "approved",
            "risk_level": "low",
            "account_type": "personal_checking",
            "missing_docs": [],
            "identity_mismatches": [],
            "aml_flags": [],
            "compliance_notes": "Standard low-risk individual application.",
            "next_steps": ["Account will be created within 1-2 business days."],
            "summary": "Application approved. All KYC checks passed with no issues.",
            "audit_key": "audit:APP-20260422-001",
        })

        responses = iter([
            intake_response,
            doc_response,
            identity_response,
            aml_response,
            risk_response,
            final_response,
        ])

        mock_session_service = AsyncMock(spec=RedisSessionService)
        mock_session = MagicMock()
        mock_session.state = {"final_decision": final_response}
        mock_session_service.create_session = AsyncMock(return_value=mock_session)
        mock_session_service.get_session = AsyncMock(return_value=mock_session)
        mock_session_service.append_event = AsyncMock()

        agent = BankingOnboardingAgent(session_service=mock_session_service)

        call_order: list[str] = []
        original_run = agent._run_agent

        async def mock_run_agent(ag, session_id, user_id, message):
            call_order.append(ag.name)
            return next(responses, "{}")

        agent._run_agent = mock_run_agent

        application_input = json.dumps({
            "application_id": "APP-20260422-001",
            "full_name": "Sarah Johnson",
            "date_of_birth": "1988-03-15",
            "nationality": "US",
            "country_of_residence": "US",
            "id_type": "passport",
            "id_number": "P12345678",
            "id_expiry_date": "2030-03-15",
            "address": "123 Oak Street, New York, NY 10001, USA",
            "phone_number": "+1-212-555-0100",
            "email": "sarah@email.com",
            "account_type": "personal_checking",
            "source_of_funds": "employment",
            "employment_status": "employed",
            "annual_income": 75000.0,
            "documents_provided": ["government_id", "proof_of_address", "proof_of_income"],
        })

        state = await agent.process_application(
            application_input=application_input,
            session_id="test_session_001",
            user_id="test_user",
        )

        # Verify all 6 agents were called in pipeline order
        assert "IntakeAgent" in call_order
        assert "DocumentAgent" in call_order
        assert "IdentityAgent" in call_order
        assert "AMLAgent" in call_order
        assert "RiskAgent" in call_order
        assert "AuditAgent" in call_order

        # Verify IntakeAgent runs before all others
        assert call_order.index("IntakeAgent") == 0

        # Verify AuditAgent is last
        assert call_order.index("AuditAgent") == len(call_order) - 1

        # Verify parallel stage: both Identity and AML appear before Risk
        assert call_order.index("IdentityAgent") < call_order.index("RiskAgent")
        assert call_order.index("AMLAgent") < call_order.index("RiskAgent")

        # Verify final state contains the decision
        assert "final_decision" in state
