"""Background execution helpers for embedding sync tasks."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
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


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SyncTaskAlreadyRunningError(Exception):
    """Raised when trying to enqueue a sync task while another sync is running."""

    def __init__(self, active_task_id: str | None = None):
        self.active_task_id = active_task_id
        message = "A sync task is already running"
        if active_task_id:
            message = f"A sync task is already running: {active_task_id}"
        super().__init__(message)


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
        store.record_last_sync(
            "vector_sync",
            {
                "task_id": task_id,
                "source": "embedding",
                "status": final_status,
                "completed_at": _utc_now(),
                "request": request.model_dump(),
                "github": result.github,
                "jira": result.jira,
                "total_embeddings": result.total_embeddings,
                "errors": result.errors,
            },
        )

    except Exception as exc:
        logger.exception("Embedding task %s failed", task_id)
        store.append_log(task_id, f"Task failed: {exc}", progress=100, status="failed")
    finally:
        store.release_sync_lock(task_id)


def enqueue_embedding_task(
    background_tasks: BackgroundTasks, request: SyncAllRequest
) -> str:
    """Create a task id, initialize status, and enqueue the background worker."""

    task_id = str(uuid.uuid4())
    store = RedisTaskStore()
    if not store.try_acquire_sync_lock(task_id):
        raise SyncTaskAlreadyRunningError(store.get_sync_lock_owner())
    store.create_task(task_id=task_id, source="manual")
    background_tasks.add_task(
        execute_embedding_task,
        task_id,
        request.model_dump(),
    )
    return task_id


def execute_kg_build_task(
    task_id: str,
    author_github_id: int | None = None,
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
                author_github_id=author_github_id,
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
        store.record_last_sync(
            "kg_build",
            {
                "task_id": task_id,
                "source": "kg_build",
                "status": status,
                "completed_at": _utc_now(),
                "author_github_id": author_github_id,
                "batch_size": batch_size,
                "prs_processed": processed,
                "profiles_updated": updated,
                "error_count": error_count,
                "errors": result.get("errors", []),
            },
        )

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
    author_github_id: int | None = None,
    batch_size: int = 50,
) -> str:
    """Create a task id, initialize status, and enqueue the KG build worker."""

    task_id = str(uuid.uuid4())
    store = RedisTaskStore()
    store.create_task(task_id=task_id, source="kg_build")
    background_tasks.add_task(
        execute_kg_build_task,
        task_id,
        author_github_id,
        batch_size,
    )
    return task_id


def execute_full_sync_task(
    task_id: str,
    request_payload: dict[str, Any],
    author_github_id: int | None = None,
    batch_size: int = 50,
) -> None:
    """Execute embedding sync first, then KG build, with unified task status."""

    store = RedisTaskStore()
    store.append_log(task_id, "Full sync task started", progress=2, status="running")

    try:
        request = SyncAllRequest.model_validate(request_payload)

        with Session(engine) as session:

            def update_sync_progress(progress: int, message: str) -> None:
                # Reserve 10-70 for embedding sync progress updates.
                mapped_progress = 10 + int(progress * 0.6)
                store.append_log(
                    task_id,
                    f"[Sync] {message}",
                    progress=mapped_progress,
                    status="running",
                )

            sync_result = run_sync_all_vectors(
                session=session,
                request=request,
                progress_callback=update_sync_progress,
            )

            if sync_result.status == "failed":
                store.append_log(
                    task_id,
                    "[Sync] Embedding sync failed; skipping KG build",
                    progress=100,
                    status="failed",
                )
                store.record_last_sync(
                    "vector_sync",
                    {
                        "task_id": task_id,
                        "source": "full_sync",
                        "status": "failed",
                        "completed_at": _utc_now(),
                        "request": request.model_dump(),
                        "github": sync_result.github,
                        "jira": sync_result.jira,
                        "total_embeddings": sync_result.total_embeddings,
                        "errors": sync_result.errors,
                    },
                )
                return

            store.append_log(
                task_id,
                "[KG] Starting knowledge graph build",
                progress=75,
                status="running",
            )

            graph_service = KnowledgeGraphService()
            builder = KGBuildService(session, graph_service)
            kg_result = builder.build_from_stored_vectors(
                author_github_id=author_github_id,
                batch_size=batch_size,
            )

        kg_error_count = len(kg_result.get("errors", []))
        kg_processed = kg_result.get("prs_processed", 0)
        kg_updated = kg_result.get("profiles_updated", 0)

        if sync_result.status == "completed" and kg_error_count == 0:
            final_status = "completed"
        else:
            final_status = "completed_with_errors"

        store.append_log(
            task_id,
            (
                "Full sync completed: "
                f"embeddings={sync_result.total_embeddings} "
                f"kg_prs_processed={kg_processed} "
                f"kg_profiles_updated={kg_updated} "
                f"kg_errors={kg_error_count}"
            ),
            progress=100,
            status=final_status,
        )

        completed_at = _utc_now()
        store.record_last_sync(
            "vector_sync",
            {
                "task_id": task_id,
                "source": "full_sync",
                "status": sync_result.status,
                "completed_at": completed_at,
                "request": request.model_dump(),
                "github": sync_result.github,
                "jira": sync_result.jira,
                "total_embeddings": sync_result.total_embeddings,
                "errors": sync_result.errors,
            },
        )
        store.record_last_sync(
            "kg_build",
            {
                "task_id": task_id,
                "source": "full_sync",
                "status": "completed"
                if kg_error_count == 0
                else "completed_with_errors",
                "completed_at": completed_at,
                "author_github_id": author_github_id,
                "batch_size": batch_size,
                "prs_processed": kg_processed,
                "profiles_updated": kg_updated,
                "error_count": kg_error_count,
                "errors": kg_result.get("errors", []),
            },
        )
        store.record_last_sync(
            "full_sync",
            {
                "task_id": task_id,
                "source": "full_sync",
                "status": final_status,
                "completed_at": completed_at,
                "request": request.model_dump(),
                "author_github_id": author_github_id,
                "batch_size": batch_size,
                "vector_sync": {
                    "status": sync_result.status,
                    "total_embeddings": sync_result.total_embeddings,
                },
                "kg_build": {
                    "status": "completed"
                    if kg_error_count == 0
                    else "completed_with_errors",
                    "prs_processed": kg_processed,
                    "profiles_updated": kg_updated,
                    "error_count": kg_error_count,
                },
                "errors": sync_result.errors + kg_result.get("errors", []),
            },
        )

        for error in sync_result.errors[:5]:
            store.append_log(task_id, f"Sync error: {error}")

        for error in kg_result.get("errors", [])[:5]:
            store.append_log(task_id, f"KG error: {error}")

    except Exception as exc:
        logger.exception("Full sync task %s failed", task_id)
        store.append_log(
            task_id,
            f"Full sync task failed: {exc}",
            progress=100,
            status="failed",
        )
    finally:
        store.release_sync_lock(task_id)


def enqueue_full_sync_task(
    background_tasks: BackgroundTasks,
    request: SyncAllRequest,
    author_github_id: int | None = None,
    batch_size: int = 50,
) -> str:
    """Create a task id and enqueue a chained embedding sync + KG build workflow."""

    task_id = str(uuid.uuid4())
    store = RedisTaskStore()
    if not store.try_acquire_sync_lock(task_id):
        raise SyncTaskAlreadyRunningError(store.get_sync_lock_owner())
    store.create_task(task_id=task_id, source="full_sync")
    background_tasks.add_task(
        execute_full_sync_task,
        task_id,
        request.model_dump(),
        author_github_id,
        batch_size,
    )
    return task_id
