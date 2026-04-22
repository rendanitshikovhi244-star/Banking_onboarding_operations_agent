"""
redis_tools.py
--------------
ADK tool functions for writing to the audit log and compliance queue in Redis.

Redis keys:
  audit:{application_id}       — LIST of JSON AuditEntry objects (append-only)
  compliance_review_queue      — LIST of high-risk application payloads for officer review
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(_REDIS_URL, decode_responses=True)


async def write_audit_log(
    application_id: str,
    agent_name: str,
    decision: str,
    details: str,
) -> dict:
    """
    Append an audit entry to the Redis audit log for a customer application.

    Each pipeline agent calls this tool once it has reached a decision.
    Entries are stored in chronological order and are append-only.

    Args:
        application_id: The unique application identifier.
        agent_name: Name of the agent writing the entry (e.g. "DocumentAgent").
        decision: Short decision label (e.g. "docs_complete", "aml_clear", "pep_flagged").
        details: JSON string or plain text with the full decision details.

    Returns:
        A dict with status and the Redis key that was written to.
    """
    redis_client = _get_redis()
    try:
        entry = {
            "application_id": application_id,
            "agent_name": agent_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "decision": decision,
            "details": details,
        }
        redis_key = f"audit:{application_id}"
        await redis_client.rpush(redis_key, json.dumps(entry))
        return {"status": "success", "redis_key": redis_key}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    finally:
        await redis_client.aclose()


async def push_compliance_queue(
    application_id: str,
    risk_score: float,
    risk_level: str,
    risk_factors: str,
) -> dict:
    """
    Push a high-risk application onto the compliance escalation queue in Redis.

    This queue is monitored by compliance officers for enhanced due diligence
    or final rejection decisions.

    Args:
        application_id: The unique application identifier.
        risk_score: Composite risk score (0.0–1.0).
        risk_level: "high" or "critical".
        risk_factors: JSON string or comma-separated list of risk factors.

    Returns:
        A dict with status, queue name, and current queue length.
    """
    redis_client = _get_redis()
    try:
        payload = json.dumps({
            "application_id": application_id,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "queued_at": datetime.utcnow().isoformat() + "Z",
        })
        queue_len = await redis_client.rpush("compliance_review_queue", payload)
        return {
            "status": "success",
            "queue": "compliance_review_queue",
            "queue_length": queue_len,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    finally:
        await redis_client.aclose()


async def get_audit_log(application_id: str) -> dict:
    """
    Retrieve all audit entries for a specific application from Redis.

    Args:
        application_id: The unique application identifier.

    Returns:
        A dict with status, application_id, entry_count, and list of entries.
    """
    redis_client = _get_redis()
    try:
        raw_entries = await redis_client.lrange(f"audit:{application_id}", 0, -1)
        entries = []
        for raw in raw_entries:
            try:
                entries.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                entries.append({"raw": raw})
        return {
            "status": "success",
            "application_id": application_id,
            "entry_count": len(entries),
            "entries": entries,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    finally:
        await redis_client.aclose()
