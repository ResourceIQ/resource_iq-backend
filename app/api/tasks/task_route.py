"""Task endpoints for async embedding workflows and SSE status updates."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.embedding.embedding_sync_service import SyncAllRequest
from app.api.tasks.task_scheduler import (
    get_schedule_status,
    list_schedule_statuses,
    schedule_embedding_task,
    schedule_full_sync_task,
    unschedule_embedding_task,
    unschedule_full_sync_task,
)
from app.api.tasks.task_service import (
    SyncTaskAlreadyRunningError,
    enqueue_embedding_task,
    enqueue_full_sync_task,
    enqueue_kg_build_task,
)
from app.api.tasks.task_store import RedisTaskStore
from app.api.user.user_model import Role
from app.utils.deps import RoleChecker

router = APIRouter(prefix="/tasks", tags=["Tasks"])


class EmbeddingTaskResponse(BaseModel):
    task_id: str
    status: str


class KGTaskRequest(BaseModel):
    author_github_id: int | None = None
    batch_size: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Max PRs to process per author during KG build",
    )


class KGTaskResponse(BaseModel):
    task_id: str
    status: str


class FullSyncTaskRequest(BaseModel):
    sync_request: SyncAllRequest = Field(default_factory=SyncAllRequest)
    author_github_id: int | None = None
    batch_size: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Max PRs to process per author during KG build",
    )


class FullSyncTaskResponse(BaseModel):
    task_id: str
    status: str


class TaskSnapshot(BaseModel):
    task_id: str
    status: str
    progress: int
    log: str
    source: str
    schedule_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SyncSummary(BaseModel):
    sync_type: str
    status: str
    task_id: str | None = None
    source: str | None = None
    completed_at: str | None = None
    updated_at: str | None = None
    request: dict[str, Any] | None = None
    total_embeddings: int | None = None
    github: dict[str, Any] | None = None
    jira: dict[str, Any] | None = None
    vector_sync: dict[str, Any] | None = None
    kg_build: dict[str, Any] | None = None
    author_github_id: int | None = None
    batch_size: int | None = None
    prs_processed: int | None = None
    profiles_updated: int | None = None
    error_count: int | None = None
    errors: list[str] = Field(default_factory=list)


class ScheduleSnapshot(BaseModel):
    schedule_id: str
    schedule_type: str
    status: str
    interval_minutes: int
    next_run_time: str | None = None
    payload: dict[str, Any]
    created_at: str | None = None
    updated_at: str | None = None


class TaskOverviewResponse(BaseModel):
    sync_in_progress: bool
    active_task: TaskSnapshot | None = None
    latest_vector_sync: SyncSummary | None = None
    latest_kg_build: SyncSummary | None = None
    latest_full_sync: SyncSummary | None = None
    next_scheduled_run_time: str | None = None
    schedules: list[ScheduleSnapshot] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ScheduleEmbeddingTaskRequest(BaseModel):
    interval_minutes: int = Field(
        ..., ge=1, description="How often to run embedding sync tasks"
    )
    sync_request: SyncAllRequest = Field(default_factory=SyncAllRequest)


class ScheduleEmbeddingTaskResponse(BaseModel):
    schedule_id: str
    schedule_type: str
    interval_minutes: int
    next_run_time: str | None = None


class ScheduleFullSyncTaskRequest(BaseModel):
    interval_minutes: int = Field(..., ge=1, description="How often to run full sync")
    sync_request: SyncAllRequest = Field(default_factory=SyncAllRequest)
    author_github_id: int | None = None
    batch_size: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Max PRs to process per author during KG build",
    )


class ScheduleFullSyncTaskResponse(BaseModel):
    schedule_id: str
    schedule_type: str
    interval_minutes: int
    next_run_time: str | None = None


@router.post(
    "/embeddings",
    response_model=EmbeddingTaskResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def trigger_embedding_task(
    background_tasks: BackgroundTasks,
    request: SyncAllRequest | None = None,
) -> EmbeddingTaskResponse:
    """Queue an async embedding task and return a task id."""

    req = request or SyncAllRequest()
    try:
        task_id = enqueue_embedding_task(background_tasks, req)
    except SyncTaskAlreadyRunningError as exc:
        detail = "A sync task is already running"
        if exc.active_task_id:
            detail = f"A sync task is already running: {exc.active_task_id}"
        raise HTTPException(status_code=409, detail=detail)
    return EmbeddingTaskResponse(task_id=task_id, status="queued")


@router.post(
    "/kg/build",
    response_model=KGTaskResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def trigger_kg_build_task(
    background_tasks: BackgroundTasks,
    request: KGTaskRequest | None = None,
) -> KGTaskResponse:
    """Queue an async KG build task and return a task id."""

    req = request or KGTaskRequest()
    task_id = enqueue_kg_build_task(
        background_tasks=background_tasks,
        author_github_id=req.author_github_id,
        batch_size=req.batch_size,
    )
    return KGTaskResponse(task_id=task_id, status="queued")


@router.post(
    "/full-sync",
    response_model=FullSyncTaskResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def trigger_full_sync_task(
    background_tasks: BackgroundTasks,
    request: FullSyncTaskRequest | None = None,
) -> FullSyncTaskResponse:
    """Queue one background task that runs vector sync first, then KG build."""

    req = request or FullSyncTaskRequest()
    try:
        task_id = enqueue_full_sync_task(
            background_tasks=background_tasks,
            request=req.sync_request,
            author_github_id=req.author_github_id,
            batch_size=req.batch_size,
        )
    except SyncTaskAlreadyRunningError as exc:
        detail = "A sync task is already running"
        if exc.active_task_id:
            detail = f"A sync task is already running: {exc.active_task_id}"
        raise HTTPException(status_code=409, detail=detail)
    return FullSyncTaskResponse(task_id=task_id, status="queued")


@router.get(
    "/status/{task_id}",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def stream_task_status(task_id: str) -> StreamingResponse:
    """Stream task progress and logs as Server-Sent Events."""

    store = RedisTaskStore()

    async def event_stream() -> Any:
        log_index = 0
        idle_ticks = 0

        while True:
            state = await asyncio.to_thread(store.get_task, task_id)
            if not state:
                payload = {
                    "progress": 0,
                    "log": "Task not found",
                    "status": "not_found",
                }
                yield f"data: {json.dumps(payload)}\n\n"
                break

            logs, log_index = await asyncio.to_thread(
                store.get_logs_since,
                task_id,
                log_index,
            )

            if logs:
                idle_ticks = 0
                for log_line in logs:
                    payload = {
                        "progress": state["progress"],
                        "log": log_line,
                        "status": state["status"],
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
            else:
                idle_ticks += 1
                if idle_ticks % 3 == 0:
                    payload = {
                        "progress": state["progress"],
                        "log": state["log"],
                        "status": state["status"],
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

            if state["status"] in {"completed", "completed_with_errors", "failed"}:
                break

            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/embeddings/schedule",
    response_model=ScheduleEmbeddingTaskResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def create_embedding_schedule(
    request: ScheduleEmbeddingTaskRequest,
) -> ScheduleEmbeddingTaskResponse:
    """Create a recurring schedule for embedding tasks."""

    schedule = schedule_embedding_task(
        interval_minutes=request.interval_minutes,
        payload=request.sync_request.model_dump(),
    )
    return ScheduleEmbeddingTaskResponse(**schedule)


@router.get(
    "/embeddings/schedule/{schedule_id}",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_embedding_schedule(schedule_id: str) -> dict[str, Any]:
    """Return scheduler metadata for a specific schedule id."""

    schedule_data = get_schedule_status(schedule_id)
    if not schedule_data:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule_data


@router.delete("/embeddings/schedule/{schedule_id}")
async def cancel_embedding_schedule(schedule_id: str) -> dict[str, str]:
    """Cancel a recurring embedding schedule."""

    removed = unschedule_embedding_task(schedule_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "cancelled", "schedule_id": schedule_id}


@router.post(
    "/full-sync/schedule",
    response_model=ScheduleFullSyncTaskResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def create_full_sync_schedule(
    request: ScheduleFullSyncTaskRequest,
) -> ScheduleFullSyncTaskResponse:
    """Create a recurring schedule for full sync tasks (embeddings + KG build)."""

    schedule = schedule_full_sync_task(
        interval_minutes=request.interval_minutes,
        payload=request.sync_request.model_dump(),
        author_github_id=request.author_github_id,
        batch_size=request.batch_size,
    )
    return ScheduleFullSyncTaskResponse(**schedule)


@router.get(
    "/full-sync/schedule/{schedule_id}",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_full_sync_schedule(schedule_id: str) -> dict[str, Any]:
    """Return scheduler metadata for a specific full sync schedule id."""

    schedule_data = get_schedule_status(schedule_id)
    if not schedule_data:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if schedule_data.get("schedule_type") != "full_sync":
        raise HTTPException(status_code=400, detail="Schedule type mismatch")
    return schedule_data


@router.delete(
    "/full-sync/schedule/{schedule_id}",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def cancel_full_sync_schedule(schedule_id: str) -> dict[str, str]:
    """Cancel a recurring full sync schedule."""

    removed = unschedule_full_sync_task(schedule_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "cancelled", "schedule_id": schedule_id}


@router.get(
    "/overview",
    response_model=TaskOverviewResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_task_overview() -> TaskOverviewResponse:
    """Return the current sync state, latest sync results, and schedule timings."""

    store = RedisTaskStore()
    active_task_id = store.get_sync_lock_owner()
    active_task = store.get_task(active_task_id) if active_task_id else None

    schedules_raw = list_schedule_statuses()
    schedules = [ScheduleSnapshot(**schedule) for schedule in schedules_raw]

    next_run_time: str | None = None
    future_times: list[datetime] = []
    for schedule in schedules:
        if schedule.status != "active" or not schedule.next_run_time:
            continue
        try:
            future_times.append(datetime.fromisoformat(schedule.next_run_time))
        except ValueError:
            continue

    if future_times:
        next_run_time = min(future_times).isoformat()

    def _load_summary(sync_type: str) -> SyncSummary | None:
        latest = store.get_last_sync(sync_type)
        if not latest:
            return None
        summary = latest.get("summary", {})
        return SyncSummary(
            sync_type=latest.get("sync_type", sync_type),
            updated_at=latest.get("updated_at"),
            **summary,
        )

    notes: list[str] = []
    if active_task:
        notes.append("A sync task is currently running.")
    else:
        notes.append("No sync task is currently running.")

    if not schedules:
        notes.append("No recurring sync schedules are configured.")

    return TaskOverviewResponse(
        sync_in_progress=active_task is not None,
        active_task=TaskSnapshot(**active_task) if active_task else None,
        latest_vector_sync=_load_summary("vector_sync"),
        latest_kg_build=_load_summary("kg_build"),
        latest_full_sync=_load_summary("full_sync"),
        next_scheduled_run_time=next_run_time,
        schedules=schedules,
        notes=notes,
    )
