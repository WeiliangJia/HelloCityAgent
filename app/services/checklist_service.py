"""Checklist generation and monitoring service"""
import asyncio
import uuid
from datetime import datetime, timezone


async def wait_for_celery_result(celery_app, task_id: str) -> dict:
    """Poll Celery for task completion without blocking event loop"""
    try:
        while True:
            await asyncio.sleep(1)
            async_result = celery_app.AsyncResult(task_id)

            if not async_result.ready():
                continue

            if async_result.successful():
                result_payload = async_result.result
                if hasattr(result_payload, "model_dump"):
                    result_payload = result_payload.model_dump()
                elif hasattr(result_payload, "dict"):
                    result_payload = result_payload.dict()
                return {
                    "status": "completed",
                    "result": result_payload,
                }

            error_message = str(async_result.info) if async_result.info else "Unknown error"
            return {
                "status": "failed",
                "error": error_message,
            }
    except Exception as monitor_error:
        return {
            "status": "failed",
            "error": str(monitor_error),
        }


async def submit_checklist_generation(celery_task, session_id: str, messages: list) -> tuple[str, str]:
    """Submit Celery checklist generation task

    Returns:
        tuple: (task_id, stable_uuid)
    """
    messages_for_celery = [
        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
        for msg in messages
    ]

    stable_uuid = str(uuid.uuid4())
    task = celery_task.delay(session_id, messages_for_celery, stable_uuid)

    return task.id, stable_uuid


def build_pending_checklist_banner(session_id: str, task_id: str, stable_uuid: str = None) -> dict:
    """Create a lightweight checklist metadata payload for in-progress generation

    IMPORTANT: Uses a stable UUID that will be reused by the final checklist
    to ensure proper status updates in the frontend.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    if not stable_uuid:
        stable_uuid = str(uuid.uuid4())

    return {
        "checklistId": stable_uuid,
        "conversationId": session_id,
        "title": "Generating your checklist",
        "summary": "Hang tight while we prepare your personalized checklist.",
        "destination": "TBD",
        "duration": "TBD",
        "stayType": "mediumTerm",
        "cityCode": "default",
        "status": "generating",
        "items": [],
        "createdAt": now_iso,
        "updatedAt": now_iso,
        "_taskId": task_id,
        "_stableUuid": stable_uuid
    }
