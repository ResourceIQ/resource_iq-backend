"""In-process scheduler for recurring embedding and full-sync jobs."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from apscheduler.jobstores.base import JobLookupError
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
    _rehydrate_active_schedules()


def stop_task_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Task scheduler stopped")


def _remove_job_if_exists(scheduler: BackgroundScheduler, job_id: str) -> bool:
    """Attempt to remove an APScheduler job and report if it was present."""

    if not scheduler.get_job(job_id):
        return False
    try:
        scheduler.remove_job(job_id)
        return True
    except JobLookupError:
        return False


def _is_schedule_active(
    store: RedisTaskStore, schedule_id: str, schedule_type: str
) -> bool:
    schedule = store.get_schedule(schedule_id)
    if not schedule:
        return False
    if str(schedule.get("schedule_type", "")) != schedule_type:
        return False
    return str(schedule.get("status", "")).lower() == "active"


def _register_embedding_job(
    scheduler: BackgroundScheduler,
    schedule_id: str,
    interval_minutes: int,
    payload: dict[str, Any],
    replace_existing: bool,
) -> None:
    job_id = _job_id(SCHEDULE_TYPE_EMBEDDING, schedule_id)
    store = RedisTaskStore()

    def _run_scheduled_task() -> None:
        if not _is_schedule_active(store, schedule_id, SCHEDULE_TYPE_EMBEDDING):
            logger.info(
                "Skipping inactive embedding schedule_id=%s and removing stale job",
                schedule_id,
            )
            _remove_job_if_exists(scheduler, job_id)
            return

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
        replace_existing=replace_existing,
    )


def _register_full_sync_job(
    scheduler: BackgroundScheduler,
    schedule_id: str,
    interval_minutes: int,
    payload: dict[str, Any],
    author_github_id: int | None,
    batch_size: int,
    replace_existing: bool,
) -> None:
    job_id = _job_id(SCHEDULE_TYPE_FULL_SYNC, schedule_id)
    store = RedisTaskStore()

    def _run_scheduled_task() -> None:
        if not _is_schedule_active(store, schedule_id, SCHEDULE_TYPE_FULL_SYNC):
            logger.info(
                "Skipping inactive full-sync schedule_id=%s and removing stale job",
                schedule_id,
            )
            _remove_job_if_exists(scheduler, job_id)
            return

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
        replace_existing=replace_existing,
    )


def _rehydrate_active_schedules() -> None:
    """Recreate in-memory APScheduler jobs from active Redis schedules."""

    scheduler = get_scheduler()
    store = RedisTaskStore()
    restored = 0

    for schedule_id in store.list_schedule_ids():
        schedule = store.get_schedule(schedule_id)
        if not schedule:
            continue

        if str(schedule.get("status", "")).lower() != "active":
            continue

        schedule_type = str(
            schedule.get("schedule_type", SCHEDULE_TYPE_EMBEDDING)
        ).lower()
        interval_minutes = int(schedule.get("interval_minutes", 0))
        if interval_minutes <= 0:
            logger.warning(
                "Skipping schedule_id=%s because interval_minutes=%s",
                schedule_id,
                schedule.get("interval_minutes"),
            )
            continue

        job_id = _job_id(schedule_type, schedule_id)
        if scheduler.get_job(job_id):
            continue

        payload_raw = schedule.get("payload", "{}")
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            logger.warning(
                "Skipping schedule_id=%s due to invalid payload JSON",
                schedule_id,
            )
            continue

        if schedule_type == SCHEDULE_TYPE_EMBEDDING:
            if not isinstance(payload, dict):
                payload = {}
            _register_embedding_job(
                scheduler=scheduler,
                schedule_id=schedule_id,
                interval_minutes=interval_minutes,
                payload=payload,
                replace_existing=False,
            )
            restored += 1
            continue

        if schedule_type == SCHEDULE_TYPE_FULL_SYNC:
            full_payload = payload if isinstance(payload, dict) else {}
            sync_payload = full_payload.get("sync_request", {})
            if not isinstance(sync_payload, dict):
                sync_payload = {}
            batch_size_raw = full_payload.get("batch_size", 50)
            try:
                batch_size = int(batch_size_raw)
            except (TypeError, ValueError):
                batch_size = 50

            _register_full_sync_job(
                scheduler=scheduler,
                schedule_id=schedule_id,
                interval_minutes=interval_minutes,
                payload=sync_payload,
                author_github_id=full_payload.get("author_github_id"),
                batch_size=batch_size,
                replace_existing=False,
            )
            restored += 1
            continue

        logger.warning(
            "Skipping schedule_id=%s due to unsupported schedule_type=%s",
            schedule_id,
            schedule_type,
        )

    if restored:
        logger.info("Rehydrated %s active schedule(s) from Redis", restored)


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
    _register_embedding_job(
        scheduler=scheduler,
        schedule_id=schedule_id,
        interval_minutes=interval_minutes,
        payload=payload,
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
    _register_full_sync_job(
        scheduler=scheduler,
        schedule_id=schedule_id,
        interval_minutes=interval_minutes,
        payload=payload,
        author_github_id=author_github_id,
        batch_size=batch_size,
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

    schedule = store.get_schedule(schedule_id)
    if schedule and str(schedule.get("schedule_type", "")) != schedule_type:
        return False

    removed_from_scheduler = _remove_job_if_exists(scheduler, job_id)
    removed_from_store = False

    if schedule:
        store.set_schedule_status(schedule_id, "cancelled")
        store.delete_schedule(schedule_id)
        removed_from_store = True

    return removed_from_scheduler or removed_from_store


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
