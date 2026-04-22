"""
model_config.py
---------------
Three-tier LiteLLM model instances.

  MODEL_FAST  — IntakeAgent, DocumentAgent
  MODEL_MID   — IdentityAgent, AMLAgent, AuditAgent
  MODEL_MAIN  — RiskAgent, OnboardingAssistant
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

load_dotenv(Path(__file__).parent.parent.parent / ".env")

MODEL_FAST = LiteLlm(model=os.environ["HF_MODEL_FAST"])
MODEL_MID  = LiteLlm(model=os.environ["HF_MODEL_MID"])
MODEL_MAIN = LiteLlm(model=os.environ["HF_MODEL_MAIN"])

DEFAULT_MODEL = MODEL_MAIN
