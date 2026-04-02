"""In-process scheduler for recurring embedding and full-sync jobs."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.api.tasks.task_service import execute_embedding_task, execute_full_sync_task
from app.api.tasks.task_store import RedisTaskStore

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

SCHEDULE_TYPE_EMBEDDING = "embedding_sync"
SCHEDULE_TYPE_FULL_SYNC = "full_sync"


def _job_id(schedule_type: str, schedule_id: str) -> str:
    if schedule_type == SCHEDULE_TYPE_FULL_SYNC:
        return f"full-sync-{schedule_id}"
    return f"embedding-sync-{schedule_id}"


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
    return _scheduler


def start_task_scheduler() -> None:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Task scheduler started")


def stop_task_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Task scheduler stopped")


def schedule_embedding_task(
    interval_minutes: int, payload: dict[str, Any]
) -> dict[str, Any]:
    """Register an interval schedule that runs the embedding sync workflow."""

    scheduler = get_scheduler()
    schedule_id = str(uuid.uuid4())
    job_id = _job_id(SCHEDULE_TYPE_EMBEDDING, schedule_id)
    store = RedisTaskStore()
    store.create_schedule(
        schedule_id,
        interval_minutes,
        payload,
        schedule_type=SCHEDULE_TYPE_EMBEDDING,
    )

    def _run_scheduled_task() -> None:
        task_id = str(uuid.uuid4())
        if not store.try_acquire_sync_lock(task_id):
            active_task_id = store.get_sync_lock_owner()
            logger.info(
                "Skipping scheduled embedding sync for schedule_id=%s because task=%s is running",
                schedule_id,
                active_task_id,
            )
            return
        store.create_task(task_id=task_id, source="scheduled", schedule_id=schedule_id)
        execute_embedding_task(
            task_id=task_id,
            request_payload=payload,
        )

    scheduler.add_job(
        _run_scheduled_task,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=job_id,
        max_instances=1,
        coalesce=True,
        replace_existing=False,
    )

    job = scheduler.get_job(job_id)
    return {
        "schedule_id": schedule_id,
        "schedule_type": SCHEDULE_TYPE_EMBEDDING,
        "interval_minutes": interval_minutes,
        "next_run_time": job.next_run_time.isoformat()
        if job and job.next_run_time
        else None,
    }


def schedule_full_sync_task(
    interval_minutes: int,
    payload: dict[str, Any],
    author_github_id: int | None = None,
    batch_size: int = 50,
) -> dict[str, Any]:
    """Register an interval schedule that runs embedding sync followed by KG build."""

    scheduler = get_scheduler()
    schedule_id = str(uuid.uuid4())
    job_id = _job_id(SCHEDULE_TYPE_FULL_SYNC, schedule_id)
    store = RedisTaskStore()

    stored_payload = {
        "sync_request": payload,
        "author_github_id": author_github_id,
        "batch_size": batch_size,
    }
    store.create_schedule(
        schedule_id,
        interval_minutes,
        stored_payload,
        schedule_type=SCHEDULE_TYPE_FULL_SYNC,
    )

    def _run_scheduled_task() -> None:
        task_id = str(uuid.uuid4())
        if not store.try_acquire_sync_lock(task_id):
            active_task_id = store.get_sync_lock_owner()
            logger.info(
                "Skipping scheduled full sync for schedule_id=%s because task=%s is running",
                schedule_id,
                active_task_id,
            )
            return
        store.create_task(
            task_id=task_id, source="scheduled_full_sync", schedule_id=schedule_id
        )
        execute_full_sync_task(
            task_id=task_id,
            request_payload=payload,
            author_github_id=author_github_id,
            batch_size=batch_size,
        )

    scheduler.add_job(
        _run_scheduled_task,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=job_id,
        max_instances=1,
        coalesce=True,
        replace_existing=False,
    )

    job = scheduler.get_job(job_id)
    return {
        "schedule_id": schedule_id,
        "schedule_type": SCHEDULE_TYPE_FULL_SYNC,
        "interval_minutes": interval_minutes,
        "next_run_time": job.next_run_time.isoformat()
        if job and job.next_run_time
        else None,
    }


def unschedule_embedding_task(schedule_id: str) -> bool:
    """Remove a scheduled embedding sync job."""

    return unschedule_task(
        schedule_id=schedule_id, schedule_type=SCHEDULE_TYPE_EMBEDDING
    )


def unschedule_full_sync_task(schedule_id: str) -> bool:
    """Remove a scheduled full sync job."""

    return unschedule_task(
        schedule_id=schedule_id, schedule_type=SCHEDULE_TYPE_FULL_SYNC
    )


def unschedule_task(schedule_id: str, schedule_type: str) -> bool:
    """Remove a scheduled job by id and schedule type."""

    scheduler = get_scheduler()
    store = RedisTaskStore()
    job_id = _job_id(schedule_type, schedule_id)
    job = scheduler.get_job(job_id)
    if not job:
        return False

    scheduler.remove_job(job_id)
    store.set_schedule_status(schedule_id, "cancelled")
    store.delete_schedule(schedule_id)
    return True


def get_schedule_status(schedule_id: str) -> dict[str, Any] | None:
    """Return Redis + scheduler metadata for a schedule id."""

    scheduler = get_scheduler()
    store = RedisTaskStore()
    schedule_data = store.get_schedule(schedule_id)
    if not schedule_data:
        return None

    schedule_type = str(schedule_data.get("schedule_type", SCHEDULE_TYPE_EMBEDDING))
    job = scheduler.get_job(_job_id(schedule_type, schedule_id))
    schedule_data["next_run_time"] = (
        job.next_run_time.isoformat() if job and job.next_run_time else None
    )
    schedule_data["payload"] = json.loads(schedule_data["payload"])
    return schedule_data


def list_schedule_statuses() -> list[dict[str, Any]]:
    """Return metadata for all currently known schedules."""

    store = RedisTaskStore()
    schedule_ids = store.list_schedule_ids()
    schedules: list[dict[str, Any]] = []
    for schedule_id in schedule_ids:
        schedule_data = get_schedule_status(schedule_id)
        if schedule_data:
            schedules.append(schedule_data)

    schedules.sort(
        key=lambda item: (
            item.get("next_run_time") is None,
            item.get("next_run_time") or "",
        )
    )
    return schedules
