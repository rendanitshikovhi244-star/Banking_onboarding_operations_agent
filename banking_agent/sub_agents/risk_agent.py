"""RiskAgent — fourth stage. Synthesises all checks into a composite risk score and routing decision."""

from google.adk.agents import LlmAgent
from ..configs import AGENT_CONFIGS, agent_start_callback
from ..tools.redis_tools import push_compliance_queue, write_audit_log

_cfg = AGENT_CONFIGS["RiskAgent"]

risk_agent = LlmAgent(
    name="RiskAgent",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[push_compliance_queue, write_audit_log],
    output_key="risk_assessment",
    before_agent_callback=agent_start_callback,
)
