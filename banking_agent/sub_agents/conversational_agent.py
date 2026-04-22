"""
OnboardingAssistant — front-door conversational agent and root_agent for `adk web`.

This agent guides customers through the banking onboarding process step-by-step,
collecting information one field at a time, verifying identity, and triggering
the full KYC pipeline when ready.
"""

from google.adk.agents import LlmAgent
from ..configs import AGENT_CONFIGS, agent_start_callback
from ..tools.document_tools import get_required_kyc_documents
from ..tools.identity_tools import verify_identity
from ..tools.pipeline_runner_tool import submit_application, resubmit_with_documents
from ..tools.redis_tools import get_audit_log

_cfg = AGENT_CONFIGS["OnboardingAssistant"]

conversational_agent = LlmAgent(
    name="OnboardingAssistant",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[
        get_required_kyc_documents,
        verify_identity,
        submit_application,
        resubmit_with_documents,
        get_audit_log,
    ],
    before_agent_callback=agent_start_callback,
)
