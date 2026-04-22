"""
logging_config.py
-----------------
Configures the banking_agent logger and provides the before_agent_callback
used by every LlmAgent to log its activation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

_LOG_FILE = Path(__file__).parent.parent.parent / "logs" / "pipeline.log"
_FMT = logging.Formatter(
    fmt="%(asctime)s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
)


def configure(level: int = logging.INFO) -> None:
    """Set up stderr + file handlers for the banking_agent namespace."""
    logger = logging.getLogger("banking_agent")
    if logger.handlers:
        return  # already configured

    console = logging.StreamHandler()
    console.setFormatter(_FMT)

    _LOG_FILE.parent.mkdir(exist_ok=True)
    _LOG_FILE.touch(exist_ok=True)
    file_h = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    file_h.setFormatter(_FMT)

    logger.setLevel(level)
    logger.addHandler(console)
    logger.addHandler(file_h)
    logger.propagate = False


def agent_start_callback(callback_context) -> Optional[object]:
    """Log agent name + model to both terminal and pipeline.log."""
    logging.getLogger("banking_agent").info(
        "[Agent] %-28s activated", callback_context.agent_name
    )
    return None
