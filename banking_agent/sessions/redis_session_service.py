"""
redis_session_service.py
------------------------
A Redis-backed ADK session service for the banking onboarding pipeline.

Redis key schema:
  adk:state:<app_name>:<user_id>:<session_id>  →  JSON dict of state
  adk:sessions:<app_name>:<user_id>            →  Redis Set of session_ids
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional

import redis.asyncio as aioredis
from google.adk.events import Event
from google.adk.sessions import Session
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)

logger = logging.getLogger("banking_agent.sessions")

_TEMP_PREFIX = "temp:"


class RedisSessionService(BaseSessionService):
    """
    Redis-backed session service that persists inter-agent state across
    pipeline stages and survives process restarts.
    """

    def __init__(self, redis_url: str, ttl: int = 86_400) -> None:
        self._redis_url = redis_url
        self._ttl = ttl
        self._sessions: dict[str, Session] = {}

    def _state_key(self, app_name: str, user_id: str, session_id: str) -> str:
        return f"adk:state:{app_name}:{user_id}:{session_id}"

    def _index_key(self, app_name: str, user_id: str) -> str:
        return f"adk:sessions:{app_name}:{user_id}"

    def _mem_key(self, app_name: str, user_id: str, session_id: str) -> str:
        return f"{app_name}:{user_id}:{session_id}"

    def _get_redis(self) -> aioredis.Redis:
        return aioredis.from_url(self._redis_url, decode_responses=True)

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict | None = None,
        session_id: str | None = None,
    ) -> Session:
        session_id = session_id or uuid.uuid4().hex
        r = self._get_redis()
        try:
            raw = await r.get(self._state_key(app_name, user_id, session_id))
            await r.sadd(self._index_key(app_name, user_id), session_id)
        finally:
            await r.aclose()

        merged: dict[str, Any] = {}
        if raw:
            merged.update(json.loads(raw))
        if state:
            merged.update(state)

        session = Session(
            id=session_id,
            app_name=app_name,
            user_id=user_id,
            state=merged,
            last_update_time=time.time(),
        )
        self._sessions[self._mem_key(app_name, user_id, session_id)] = session
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        mem_key = self._mem_key(app_name, user_id, session_id)
        session = self._sessions.get(mem_key)

        r = self._get_redis()
        try:
            raw = await r.get(self._state_key(app_name, user_id, session_id))
        finally:
            await r.aclose()

        if session is None:
            if raw is None:
                return None
            session = Session(
                id=session_id,
                app_name=app_name,
                user_id=user_id,
                state=json.loads(raw),
                last_update_time=time.time(),
            )
            self._sessions[mem_key] = session
        elif raw:
            session.state.update(json.loads(raw))

        return session

    async def list_sessions(
        self, *, app_name: str, user_id: str | None = None
    ) -> ListSessionsResponse:
        sessions = [
            s
            for s in self._sessions.values()
            if s.app_name == app_name and (user_id is None or s.user_id == user_id)
        ]
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        self._sessions.pop(self._mem_key(app_name, user_id, session_id), None)
        r = self._get_redis()
        try:
            await r.delete(self._state_key(app_name, user_id, session_id))
            await r.srem(self._index_key(app_name, user_id), session_id)
        finally:
            await r.aclose()

    async def append_event(self, session: Session, event: Event) -> Event:
        event = await super().append_event(session, event)
        if not event.partial:
            # Persist only non-temporary state keys to Redis
            persistent = {
                k: v
                for k, v in session.state.items()
                if not k.startswith(_TEMP_PREFIX)
            }
            r = self._get_redis()
            try:
                await r.set(
                    self._state_key(session.app_name, session.user_id, session.id),
                    json.dumps(persistent),
                    ex=self._ttl,
                )
            finally:
                await r.aclose()
        return event
