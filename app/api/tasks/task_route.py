"""Task endpoints for async embedding workflows and SSE status updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.embedding.embedding_sync_service import SyncAllRequest
from app.api.tasks.task_scheduler import (
    get_schedule_status,
    schedule_embedding_task,
    unschedule_embedding_task,
)
from app.api.tasks.task_service import enqueue_embedding_task
from app.api.tasks.task_store import RedisTaskStore

router = APIRouter(prefix="/tasks", tags=["Tasks"])


class EmbeddingTaskResponse(BaseModel):
    task_id: str
    status: str


class ScheduleEmbeddingTaskRequest(BaseModel):
    interval_minutes: int = Field(
        ..., ge=1, description="How often to run embedding sync tasks"
    )
    sync_request: SyncAllRequest = Field(default_factory=SyncAllRequest)


class ScheduleEmbeddingTaskResponse(BaseModel):
    schedule_id: str
    interval_minutes: int
    next_run_time: str | None = None


@router.post("/embeddings", response_model=EmbeddingTaskResponse)
async def trigger_embedding_task(
    background_tasks: BackgroundTasks,
    request: SyncAllRequest | None = None,
) -> EmbeddingTaskResponse:
    """Queue an async embedding task and return a task id."""

    req = request or SyncAllRequest()
    task_id = enqueue_embedding_task(background_tasks, req)
    return EmbeddingTaskResponse(task_id=task_id, status="queued")


@router.get("/status/{task_id}")
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


@router.post("/embeddings/schedule", response_model=ScheduleEmbeddingTaskResponse)
async def create_embedding_schedule(
    request: ScheduleEmbeddingTaskRequest,
) -> ScheduleEmbeddingTaskResponse:
    """Create a recurring schedule for embedding tasks."""

    schedule = schedule_embedding_task(
        interval_minutes=request.interval_minutes,
        payload=request.sync_request.model_dump(),
    )
    return ScheduleEmbeddingTaskResponse(**schedule)


@router.get("/embeddings/schedule/{schedule_id}")
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
