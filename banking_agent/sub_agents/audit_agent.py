"""AuditAgent — final pipeline stage. Compiles the OnboardingDecision and writes the audit trail."""

from google.adk.agents import LlmAgent
from ..configs import AGENT_CONFIGS, agent_start_callback
from ..tools.redis_tools import write_audit_log

_cfg = AGENT_CONFIGS["AuditAgent"]

audit_agent = LlmAgent(
    name="AuditAgent",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[write_audit_log],
    output_key="final_decision",
    before_agent_callback=agent_start_callback,
)
