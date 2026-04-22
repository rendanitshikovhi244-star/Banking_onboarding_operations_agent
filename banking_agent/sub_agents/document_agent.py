"""DocumentAgent — second agent. Checks required KYC documents for the account type."""

from google.adk.agents import LlmAgent
from ..configs import AGENT_CONFIGS, agent_start_callback
from ..tools.document_tools import get_required_kyc_documents, check_kyc_documents
from ..tools.redis_tools import write_audit_log

_cfg = AGENT_CONFIGS["DocumentAgent"]

document_agent = LlmAgent(
    name="DocumentAgent",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[get_required_kyc_documents, check_kyc_documents, write_audit_log],
    output_key="document_check",
    before_agent_callback=agent_start_callback,
)
