"""Redis-backed storage utilities for long-running embedding tasks."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import redis

from app.core.config import settings


class RedisTaskStore:
    """Store task status and logs in Redis for SSE streaming."""

    SYNC_LOCK_KEY = "task:sync:lock"
    SCHEDULES_INDEX_KEY = "task:schedules"

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
    def _last_sync_key(sync_type: str) -> str:
        return f"task:last_sync:{sync_type}"

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()

    def try_acquire_sync_lock(
        self,
        task_id: str,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Acquire the global sync lock if no sync workflow is currently running."""

        ttl = ttl_seconds or settings.TASK_STATUS_TTL_SECONDS
        acquired = self.client.set(self.SYNC_LOCK_KEY, task_id, nx=True, ex=ttl)
        return bool(acquired)

    def get_sync_lock_owner(self) -> str | None:
        """Return task_id owning the global sync lock, if present."""

        owner = self.client.get(self.SYNC_LOCK_KEY)
        if owner is None:
            return None
        return str(owner)

    def release_sync_lock(self, task_id: str) -> None:
        """Release the global sync lock if owned by task_id."""

        owner = self.client.get(self.SYNC_LOCK_KEY)
        if owner is not None and str(owner) == task_id:
            self.client.delete(self.SYNC_LOCK_KEY)

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
            "created_at": self._timestamp(),
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
            "created_at": raw.get("created_at"),
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
        schedule_type: str = "embedding_sync",
    ) -> None:
        data = {
            "schedule_id": schedule_id,
            "schedule_type": schedule_type,
            "status": "active",
            "interval_minutes": interval_minutes,
            "payload": json.dumps(payload),
            "created_at": self._timestamp(),
            "updated_at": self._timestamp(),
        }
        pipe = self.client.pipeline()
        pipe.hset(self._schedule_key(schedule_id), mapping=data)
        pipe.sadd(self.SCHEDULES_INDEX_KEY, schedule_id)
        pipe.execute()

    def set_schedule_status(self, schedule_id: str, status: str) -> None:
        self.client.hset(
            self._schedule_key(schedule_id),
            mapping={"status": status, "updated_at": self._timestamp()},
        )

    def delete_schedule(self, schedule_id: str) -> None:
        pipe = self.client.pipeline()
        pipe.srem(self.SCHEDULES_INDEX_KEY, schedule_id)
        pipe.delete(self._schedule_key(schedule_id))
        pipe.execute()

    def list_schedule_ids(self) -> list[str]:
        schedule_ids = cast(set[str], self.client.smembers(self.SCHEDULES_INDEX_KEY))
        return sorted(schedule_ids)

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        raw = cast(dict[str, Any], self.client.hgetall(self._schedule_key(schedule_id)))
        if not raw:
            return None
        return {
            "schedule_id": raw.get("schedule_id", schedule_id),
            "schedule_type": raw.get("schedule_type", "embedding_sync"),
            "status": raw.get("status", "unknown"),
            "interval_minutes": int(raw.get("interval_minutes", "0")),
            "payload": raw.get("payload", "{}"),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }

    def record_last_sync(self, sync_type: str, summary: dict[str, Any]) -> None:
        payload = {
            "sync_type": sync_type,
            "summary": json.dumps(summary),
            "updated_at": self._timestamp(),
        }
        self.client.hset(self._last_sync_key(sync_type), mapping=payload)

    def get_last_sync(self, sync_type: str) -> dict[str, Any] | None:
        raw = cast(dict[str, Any], self.client.hgetall(self._last_sync_key(sync_type)))
        if not raw:
            return None
        summary_raw = raw.get("summary", "{}")
        try:
            summary = json.loads(summary_raw)
        except json.JSONDecodeError:
            summary = {}
        return {
            "sync_type": raw.get("sync_type", sync_type),
            "summary": summary,
            "updated_at": raw.get("updated_at"),
        }
