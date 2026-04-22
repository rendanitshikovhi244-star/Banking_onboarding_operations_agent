from .configs.logging_config import configure as _configure_logging
_configure_logging()

from . import agent  # noqa: F401 — ensures root_agent is importable by adk run

from .agent import root_agent

__all__ = ["root_agent"]
