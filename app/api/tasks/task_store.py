"""Redis-backed storage utilities for long-running embedding tasks."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import redis

from app.core.config import settings


class RedisTaskStore:
    """Store task status and logs in Redis for SSE streaming."""

    def __init__(self) -> None:
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )

    @staticmethod
    def _task_key(task_id: str) -> str:
        return f"task:{task_id}"

    @staticmethod
    def _task_logs_key(task_id: str) -> str:
        return f"task:{task_id}:logs"

    @staticmethod
    def _schedule_key(schedule_id: str) -> str:
        return f"task:schedule:{schedule_id}"

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()

    def create_task(
        self,
        task_id: str,
        source: str = "manual",
        schedule_id: str | None = None,
    ) -> None:
        payload = {
            "task_id": task_id,
            "status": "queued",
            "progress": 0,
            "log": "Task queued",
            "source": source,
            "schedule_id": schedule_id or "",
            "updated_at": self._timestamp(),
        }
        pipe = self.client.pipeline()
        pipe.hset(self._task_key(task_id), mapping=payload)
        pipe.delete(self._task_logs_key(task_id))
        pipe.rpush(self._task_logs_key(task_id), "Task queued")
        pipe.expire(self._task_key(task_id), settings.TASK_STATUS_TTL_SECONDS)
        pipe.expire(self._task_logs_key(task_id), settings.TASK_STATUS_TTL_SECONDS)
        pipe.execute()

    def append_log(
        self,
        task_id: str,
        message: str,
        progress: int | None = None,
        status: str | None = None,
    ) -> None:
        updates: dict[str, Any] = {
            "log": message,
            "updated_at": self._timestamp(),
        }
        if progress is not None:
            updates["progress"] = max(0, min(progress, 100))
        if status:
            updates["status"] = status

        pipe = self.client.pipeline()
        pipe.hset(self._task_key(task_id), mapping=updates)
        pipe.rpush(self._task_logs_key(task_id), message)
        pipe.expire(self._task_key(task_id), settings.TASK_STATUS_TTL_SECONDS)
        pipe.expire(self._task_logs_key(task_id), settings.TASK_STATUS_TTL_SECONDS)
        pipe.execute()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        raw = cast(dict[str, Any], self.client.hgetall(self._task_key(task_id)))
        if not raw:
            return None

        return {
            "task_id": raw.get("task_id", task_id),
            "status": raw.get("status", "queued"),
            "progress": int(raw.get("progress", 0)),
            "log": raw.get("log", ""),
            "source": raw.get("source", "manual"),
            "schedule_id": raw.get("schedule_id") or None,
            "updated_at": raw.get("updated_at"),
        }

    def get_logs_since(self, task_id: str, start_index: int) -> tuple[list[str], int]:
        logs = cast(
            list[str], self.client.lrange(self._task_logs_key(task_id), start_index, -1)
        )
        new_index = start_index + len(logs)
        return logs, new_index

    def create_schedule(
        self,
        schedule_id: str,
        interval_minutes: int,
        payload: dict[str, Any],
    ) -> None:
        data = {
            "schedule_id": schedule_id,
            "status": "active",
            "interval_minutes": interval_minutes,
            "payload": json.dumps(payload),
            "updated_at": self._timestamp(),
        }
        self.client.hset(self._schedule_key(schedule_id), mapping=data)

    def set_schedule_status(self, schedule_id: str, status: str) -> None:
        self.client.hset(
            self._schedule_key(schedule_id),
            mapping={"status": status, "updated_at": self._timestamp()},
        )

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        raw = cast(dict[str, Any], self.client.hgetall(self._schedule_key(schedule_id)))
        if not raw:
            return None
        return {
            "schedule_id": raw.get("schedule_id", schedule_id),
            "status": raw.get("status", "unknown"),
            "interval_minutes": int(raw.get("interval_minutes", "0")),
            "payload": raw.get("payload", "{}"),
            "updated_at": raw.get("updated_at"),
        }
