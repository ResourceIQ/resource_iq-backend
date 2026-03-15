"""Background execution helpers for embedding sync tasks."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import BackgroundTasks
from sqlmodel import Session

from app.api.embedding.embedding_sync_service import (
    SyncAllRequest,
    run_sync_all_vectors,
)
from app.api.tasks.task_store import RedisTaskStore
from app.db.session import engine

logger = logging.getLogger(__name__)


def execute_embedding_task(
    task_id: str,
    request_payload: dict[str, Any],
) -> None:
    """Execute the embedding workflow and persist status/log updates to Redis."""

    store = RedisTaskStore()
    store.append_log(task_id, "Task started", progress=2, status="running")

    try:
        request = SyncAllRequest.model_validate(request_payload)

        with Session(engine) as session:

            def update_progress(progress: int, message: str) -> None:
                store.append_log(task_id, message, progress=progress, status="running")

            result = run_sync_all_vectors(
                session=session,
                request=request,
                progress_callback=update_progress,
            )

        final_status = result.status
        final_log = (
            "Task completed"
            if final_status == "completed"
            else "Task completed with warnings"
        )
        store.append_log(task_id, final_log, progress=100, status=final_status)

    except Exception as exc:
        logger.exception("Embedding task %s failed", task_id)
        store.append_log(task_id, f"Task failed: {exc}", progress=100, status="failed")


def enqueue_embedding_task(
    background_tasks: BackgroundTasks, request: SyncAllRequest
) -> str:
    """Create a task id, initialize status, and enqueue the background worker."""

    task_id = str(uuid.uuid4())
    store = RedisTaskStore()
    store.create_task(task_id=task_id, source="manual")
    background_tasks.add_task(
        execute_embedding_task,
        task_id,
        request.model_dump(),
    )
    return task_id
