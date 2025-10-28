from celery import Celery
from ..core.graph import get_router_graph_generate, get_router_graph_convert
import json
import uuid
from datetime import datetime, timedelta, timezone

celery_app = Celery(
    "worker",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0",
)

# Configure task result expiration (1 hour)
# Prevents Redis OOM by auto-deleting completed task results
celery_app.conf.result_expires = 3600  # 1 hour in seconds


def _map_importance(value: str) -> str:
    if not value:
        return "medium"
    normalized = value.lower()
    mapping = {
        "urgent": "high",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }
    return mapping.get(normalized, "medium")


def _map_stay_type(value: str) -> str:
    if not value:
        return "longTerm"
    normalized = value.lower()
    mapping = {
        "short-term": "shortTerm",
        "shortterm": "shortTerm",
        "medium-term": "mediumTerm",
        "mediumterm": "mediumTerm",
        "long-term": "longTerm",
        "longterm": "longTerm",
    }
    return mapping.get(normalized, "longTerm")


def _build_frontend_checklist(session_id: str, generated_checklist: dict, stable_uuid: str = None) -> dict:
    now = datetime.now(timezone.utc)
    # Use provided stable UUID or generate a new one
    if not stable_uuid:
        stable_uuid = str(uuid.uuid4())
    checklist_id = stable_uuid

    items_payload = []
    generated_items = generated_checklist.get("items", []) or []
    for idx, item in enumerate(generated_items):
        due_days_raw = item.get("due_days", 0)
        try:
            due_days_int = int(due_days_raw)
        except (TypeError, ValueError):
            due_days_int = 0

        due_date = (now + timedelta(days=due_days_int)).date().isoformat()

        items_payload.append({
            "title": (item.get("title") or "").strip(),
            "description": (item.get("description") or "").strip(),
            "importance": _map_importance(item.get("importance", "")),
            "dueDate": due_date,
            "category": (item.get("category") or "General").strip(),
            "order": item.get("order", idx),
            "isComplete": False,
        })

    city_info = generated_checklist.get("city_info", {}) or {}

    frontend_payload = {
        "checklistId": checklist_id,
        "conversationId": session_id,
        "title": (generated_checklist.get("title") or "").strip(),
        "summary": (generated_checklist.get("summary") or "").strip(),
        "destination": (generated_checklist.get("destination") or "").strip(),
        "duration": (generated_checklist.get("duration") or "").strip(),
        "stayType": _map_stay_type(generated_checklist.get("stay_type", "")),
        "cityCode": city_info.get("city_code", "unknown"),
        "status": "completed",
        "items": items_payload,
        "createdAt": now.isoformat(),
        "updatedAt": now.isoformat(),
    }

    return frontend_payload

@celery_app.task
def create_checklist_items(session_id, messages, stable_uuid=None):
    import time
    task_start_time = time.time()
    print(f"\n[CELERY TIMING] Task started at: {task_start_time:.3f}")
    def _normalize_dict(value):
        if not value:
            return None
        if hasattr(value, "model_dump"):
            try:
                return value.model_dump()
            except Exception as err:
                print(f"[CELERY WARNING] model_dump failed: {err}")
                return None
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                print("[CELERY WARNING] Failed to parse string as JSON")
                return None
        return None

    def _extract_checklist_from_messages(messages):
        for message in reversed(messages or []):
            content = (
                message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
            )
            parsed = _normalize_dict(content)
            if parsed and parsed.get("items"):
                return parsed
        return None

    def _extract_metadata_from_messages(messages):
        for message in reversed(messages or []):
            content = (
                message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
            )
            parsed = _normalize_dict(content)
            if parsed and not parsed.get("items"):
                return parsed
        return None

    generation_graph = get_router_graph_generate()
    conversion_graph = get_router_graph_convert()

    # Stage 1: checklist generation
    generation_start_time = time.time()
    print(f"[CELERY TIMING] Generation stage starting at: {generation_start_time:.3f} (elapsed: {generation_start_time - task_start_time:.3f}s)")

    generation_result = generation_graph.invoke(
        {"messages": messages},
        config={
            "configurable": {"thread_id": f"{session_id}-generate"},
            "recursion_limit": 100  # Increased for nested agent (websearch + react cycles)
        }
    )
    generation_end_time = time.time()
    print(f"[CELERY TIMING] Generation completed at: {generation_end_time:.3f} (duration: {generation_end_time - generation_start_time:.3f}s)")
    print(f"[CELERY DEBUG] Generation result type: {type(generation_result)}")

    generation_messages = []
    if isinstance(generation_result, dict):
        generation_messages = generation_result.get("messages", []) or []
    generated_checklist = (
        _normalize_dict(generation_result.get("generated_checklist"))
        if isinstance(generation_result, dict)
        else None
    )
    if not generated_checklist:
        generated_checklist = _extract_checklist_from_messages(generation_messages) or _extract_checklist_from_messages(messages)

    # Stage 2: metadata conversion (feed the generator output back in)
    conversion_start_time = time.time()
    print(f"[CELERY TIMING] Conversion stage starting at: {conversion_start_time:.3f} (elapsed: {conversion_start_time - task_start_time:.3f}s)")

    conversion_input = {
        "messages": generation_messages or messages,
        "generated_checklist": generated_checklist,
    }
    conversion_result = conversion_graph.invoke(
        conversion_input,
        config={"configurable": {"thread_id": f"{session_id}-convert"}}
    )

    conversion_end_time = time.time()
    print(f"[CELERY TIMING] Conversion completed at: {conversion_end_time:.3f} (duration: {conversion_end_time - conversion_start_time:.3f}s)")
    print(f"[CELERY DEBUG] Conversion result type: {type(conversion_result)}")

    conversion_messages = []
    if isinstance(conversion_result, dict):
        conversion_messages = conversion_result.get("messages", []) or []
    checklist_data = (
        _normalize_dict(conversion_result.get("checklist_data"))
        if isinstance(conversion_result, dict)
        else None
    )
    if not checklist_data:
        combined_for_metadata = conversion_messages or generation_messages
        checklist_data = _extract_metadata_from_messages(combined_for_metadata)

    # Debug output
    if generated_checklist:
        print(" FULL GENERATED CHECKLIST (Pretty JSON):")
        print("=" * 60)
        print(json.dumps(generated_checklist, indent=2, ensure_ascii=False))
        print("=" * 60)
    else:
        print("[CELERY WARNING] Generated checklist missing after generation stage")

    if checklist_data:
        print(" CHECKLIST METADATA (Pretty JSON):")
        print("=" * 60)
        print(json.dumps(checklist_data, indent=2, ensure_ascii=False))
        print("=" * 60)
    else:
        print("[CELERY WARNING] Checklist metadata missing after conversion stage")

    task_end_time = time.time()
    print(f"[CELERY TIMING] Task completed at: {task_end_time:.3f} (total duration: {task_end_time - task_start_time:.3f}s)")
    print(f"Background graph processing completed for session: {session_id}")

    if generated_checklist:
        print("[SUCCESS] Returning generated checklist to Frontend")
        try:
            frontend_payload = _build_frontend_checklist(session_id, generated_checklist, stable_uuid)
            print(f"[DEBUG] Frontend payload checklistId: {frontend_payload.get('checklistId')}")
            print(f"[DEBUG] Frontend payload status: {frontend_payload.get('status')}")
            return frontend_payload
        except Exception as transform_error:
            print(f"[ERROR] Failed to transform generated checklist: {transform_error}")
            return {"error": "Failed to transform generated checklist", "session_id": session_id}

    if checklist_data:
        print("[SUCCESS] Returning checklist metadata to Frontend")
        return checklist_data

    print("[WARNING] No checklist data found, returning error")
    return {"error": "No checklist data generated", "session_id": session_id}
