"""
Task management endpoints for async checklist generation
"""
from fastapi import APIRouter, HTTPException
from ...models.schemas import TaskSubmitRequest, TaskSubmitResponse, TaskStatusResponse
from ..tasks import create_checklist_items, celery_app

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/submit", response_model=TaskSubmitResponse)
async def submit_task(request: TaskSubmitRequest):
    """
    Submit a checklist generation task to Celery

    NOTE: This endpoint is currently NOT used in production flow.
    Production uses direct Celery call in main.py:237 when tool call is detected.

    Use cases:
    - Manual testing: curl -X POST http://localhost:8000/tasks/submit ...
    - Future feature: Manual retry or independent checklist generation
    - Debugging: Trigger tasks without going through chat flow

    Args:
        request: TaskSubmitRequest with conversationId and messages

    Returns:
        TaskSubmitResponse with taskId and status
    """
    try:
        # Trigger Celery task asynchronously
        task = create_checklist_items.delay(
            request.conversationId,
            request.messages
        )

        print(f"[INFO] Task submitted: {task.id} for conversation {request.conversationId}")

        return TaskSubmitResponse(
            taskId=task.id,
            status="pending"
        )

    except Exception as e:
        print(f"[ERROR] Failed to submit task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {str(e)}")


@router.get("/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Get the status of a Celery task

    Args:
        task_id: Celery task ID

    Returns:
        TaskStatusResponse with status and result
    """
    try:
        # Get task result from Celery
        task_result = celery_app.AsyncResult(task_id)

        # Map Celery states to our status
        status_mapping = {
            "PENDING": "pending",
            "STARTED": "generating",
            "SUCCESS": "completed",
            "FAILURE": "failed",
            "RETRY": "generating",
        }

        status = status_mapping.get(task_result.state, "pending")

        response = TaskStatusResponse(
            taskId=task_id,
            status=status,
        )

        # Add result if completed
        if status == "completed":
            response.result = task_result.result if task_result.result else None

        # Add error if failed
        if status == "failed":
            response.error = str(task_result.info) if task_result.info else "Unknown error"

        print(f"[INFO] Task {task_id} status: {status}")

        return response

    except Exception as e:
        print(f"[ERROR] Failed to get task status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")
