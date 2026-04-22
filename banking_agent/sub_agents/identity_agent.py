"""IdentityAgent — runs in parallel with AMLAgent. Cross-checks identity details."""

from google.adk.agents import LlmAgent
from ..configs import AGENT_CONFIGS, agent_start_callback
from ..tools.identity_tools import verify_identity, check_id_expiry
from ..tools.redis_tools import write_audit_log

_cfg = AGENT_CONFIGS["IdentityAgent"]

identity_agent = LlmAgent(
    name="IdentityAgent",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[verify_identity, check_id_expiry, write_audit_log],
    output_key="identity_verification",
    before_agent_callback=agent_start_callback,
)
