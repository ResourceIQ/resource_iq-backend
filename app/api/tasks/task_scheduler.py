"""In-process scheduler for recurring embedding sync jobs."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.api.tasks.task_service import execute_embedding_task
from app.api.tasks.task_store import RedisTaskStore

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


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
    job_id = f"embedding-sync-{schedule_id}"
    store = RedisTaskStore()
    store.create_schedule(schedule_id, interval_minutes, payload)

    def _run_scheduled_task() -> None:
        task_id = str(uuid.uuid4())
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
        "interval_minutes": interval_minutes,
        "next_run_time": job.next_run_time.isoformat()
        if job and job.next_run_time
        else None,
    }


def unschedule_embedding_task(schedule_id: str) -> bool:
    """Remove a scheduled embedding sync job."""

    scheduler = get_scheduler()
    store = RedisTaskStore()
    job_id = f"embedding-sync-{schedule_id}"
    job = scheduler.get_job(job_id)
    if not job:
        return False

    scheduler.remove_job(job_id)
    store.set_schedule_status(schedule_id, "cancelled")
    return True


def get_schedule_status(schedule_id: str) -> dict[str, Any] | None:
    """Return Redis + scheduler metadata for a schedule id."""

    scheduler = get_scheduler()
    store = RedisTaskStore()
    schedule_data = store.get_schedule(schedule_id)
    if not schedule_data:
        return None

    job = scheduler.get_job(f"embedding-sync-{schedule_id}")
    schedule_data["next_run_time"] = (
        job.next_run_time.isoformat() if job and job.next_run_time else None
    )
    schedule_data["payload"] = json.loads(schedule_data["payload"])
    return schedule_data
