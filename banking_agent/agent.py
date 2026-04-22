"""
agent.py
--------
BankingOnboardingAgent — orchestrates the full KYC onboarding pipeline.

Pipeline stages (executed in order):
  1. IntakeAgent          — normalise raw input → CustomerIntake (session: normalized_application)
  2. DocumentAgent        — KYC document completeness check    (session: document_check)
  3. IdentityAgent        — identity field cross-check          (session: identity_verification)  ┐ parallel
     AMLAgent             — PEP / sanctions / AML screening     (session: aml_screening)          ┘
  4. RiskAgent            — composite risk score + routing      (session: risk_assessment)
  5. AuditAgent           — final decision + audit trail        (session: final_decision)

The conversational OnboardingAssistant is exposed as root_agent for `adk web`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types

from .sessions import RedisSessionService

from .sub_agents import (
    audit_agent,
    document_agent,
    identity_agent,
    aml_agent,
    risk_agent,
    intake_agent,
)
from .sub_agents.conversational_agent import conversational_agent

logger = logging.getLogger("banking_agent.onboarding")


class BankingOnboardingAgent:
    APP_NAME = "banking_onboarding"

    def __init__(self, session_service: BaseSessionService | None = None) -> None:
        if session_service is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            session_service = RedisSessionService(redis_url=redis_url)
        self.session_service = session_service
        self.intake_agent = intake_agent
        self.document_agent = document_agent
        self.identity_agent = identity_agent
        self.aml_agent = aml_agent
        self.risk_agent = risk_agent
        self.audit_agent = audit_agent
        self._root_agent = conversational_agent

    async def _run_agent(
        self,
        agent: LlmAgent,
        session_id: str,
        user_id: str,
        message: str,
    ) -> str | None:
        runner = Runner(
            agent=agent,
            app_name=self.APP_NAME,
            session_service=self.session_service,
        )
        content = types.Content(role="user", parts=[types.Part(text=message)])
        final_text: str | None = None

        logger.info("[Pipeline] %-28s → running", agent.name)
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            if event.actions and event.actions.state_delta:
                for key, val in event.actions.state_delta.items():
                    logger.debug("[State] %s ← %s", key, str(val)[:120])
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        logger.debug(
                            "[Tool] %s(%s)",
                            part.function_call.name,
                            str(part.function_call.args)[:80],
                        )
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        final_text = part.text.strip()
                        break

        logger.info("[Pipeline] %-28s   complete", agent.name)
        return final_text

    async def process_application(
        self,
        application_input: str,
        *,
        session_id: str | None = None,
        user_id: str = "system",
    ) -> dict[str, Any]:
        """
        Execute the full KYC onboarding pipeline for a single application.

        Args:
            application_input: Raw application — JSON string or free-text description.
            session_id: Optional session identifier (generated if not provided).
            user_id: Identifier for the submitting user/system.

        Returns:
            The final session state dict after all pipeline stages complete.
        """
        session_id = session_id or f"onboarding_{uuid.uuid4().hex[:12]}"

        await self.session_service.create_session(
            app_name=self.APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )

        # Stage 1 — Intake: normalise raw application data
        await self._run_agent(
            self.intake_agent,
            session_id,
            user_id,
            application_input,
        )

        # Stage 2 — Document check: identify required and missing KYC docs
        await self._run_agent(
            self.document_agent,
            session_id,
            user_id,
            "Check the required KYC documents for this application.",
        )

        # Stage 3 — Identity verification + AML screening (concurrent)
        await asyncio.gather(
            self._run_agent(
                self.identity_agent,
                session_id,
                user_id,
                "Verify the applicant's identity details and flag any mismatches.",
            ),
            self._run_agent(
                self.aml_agent,
                session_id,
                user_id,
                "Perform AML screening: check PEP status, sanctions lists, and adverse media.",
            ),
        )

        # Stage 4 — Risk assessment: composite scoring and routing decision
        await self._run_agent(
            self.risk_agent,
            session_id,
            user_id,
            "Assess the overall customer risk level and determine the appropriate routing decision.",
        )

        # Stage 5 — Audit: compile final onboarding decision + write audit trail
        await self._run_agent(
            self.audit_agent,
            session_id,
            user_id,
            "Compile the final onboarding decision and write the complete audit summary.",
        )

        session = await self.session_service.get_session(
            app_name=self.APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        return dict(session.state) if session else {}


banking_onboarding_agent = BankingOnboardingAgent()
root_agent = banking_onboarding_agent._root_agent
