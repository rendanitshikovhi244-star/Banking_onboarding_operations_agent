"""AMLAgent — runs in parallel with IdentityAgent. PEP, sanctions, and AML screening."""

from google.adk.agents import LlmAgent
from ..configs import AGENT_CONFIGS, agent_start_callback
from ..tools.aml_tools import (
    check_pep_status,
    check_sanctions_list,
    check_adverse_media,
    screen_high_risk_jurisdiction,
)
from ..tools.redis_tools import write_audit_log

_cfg = AGENT_CONFIGS["AMLAgent"]

aml_agent = LlmAgent(
    name="AMLAgent",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[
        check_pep_status,
        check_sanctions_list,
        check_adverse_media,
        screen_high_risk_jurisdiction,
        write_audit_log,
    ],
    output_key="aml_screening",
    before_agent_callback=agent_start_callback,
)
