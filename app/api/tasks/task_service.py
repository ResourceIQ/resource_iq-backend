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
from app.api.knowledge_graph.kg_build_service import KGBuildService
from app.api.knowledge_graph.kg_service import KnowledgeGraphService
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


def execute_kg_build_task(
    task_id: str,
    author_login: str | None = None,
    batch_size: int = 50,
) -> None:
    """Execute KG build workflow and persist status/log updates to Redis."""

    store = RedisTaskStore()
    store.append_log(task_id, "KG build task started", progress=2, status="running")

    try:
        with Session(engine) as session:
            graph_service = KnowledgeGraphService()
            builder = KGBuildService(session, graph_service)
            result = builder.build_from_stored_vectors(
                author_login=author_login,
                batch_size=batch_size,
            )

        error_count = len(result.get("errors", []))
        processed = result.get("prs_processed", 0)
        updated = result.get("profiles_updated", 0)

        if error_count == 0:
            status = "completed"
            summary = f"KG build completed: prs_processed={processed} profiles_updated={updated}"
        else:
            status = "completed_with_errors"
            summary = (
                f"KG build completed with errors: prs_processed={processed} "
                f"profiles_updated={updated} errors={error_count}"
            )

        store.append_log(task_id, summary, progress=100, status=status)

        for error in result.get("errors", [])[:5]:
            store.append_log(task_id, f"KG error: {error}")

    except Exception as exc:
        logger.exception("KG build task %s failed", task_id)
        store.append_log(
            task_id,
            f"KG build task failed: {exc}",
            progress=100,
            status="failed",
        )


def enqueue_kg_build_task(
    background_tasks: BackgroundTasks,
    author_login: str | None = None,
    batch_size: int = 50,
) -> str:
    """Create a task id, initialize status, and enqueue the KG build worker."""

    task_id = str(uuid.uuid4())
    store = RedisTaskStore()
    store.create_task(task_id=task_id, source="kg_build")
    background_tasks.add_task(
        execute_kg_build_task,
        task_id,
        author_login,
        batch_size,
    )
    return task_id
