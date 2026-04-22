"""IntakeAgent — first agent in the KYC pipeline. Normalises raw input."""

from google.adk.agents import LlmAgent
from ..configs import AGENT_CONFIGS, agent_start_callback

_cfg = AGENT_CONFIGS["IntakeAgent"]

intake_agent = LlmAgent(
    name="IntakeAgent",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    output_key="normalized_application",
    before_agent_callback=agent_start_callback,
)
