from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator, Optional
import json
import asyncio
import time
import os
import uuid
from langchain_core.language_models import BaseChatModel

from ..models.schemas import AskRequest, GenerateTitleRequest, GenerateTitleResponse
from ..core.graph import get_router_graph_chat
from ..config.dependencies import get_llm, get_llm_chat
from ..services.message_service import validate_messages, convert_to_langchain_messages
from ..services.checklist_service import (
    wait_for_celery_result,
    submit_checklist_generation,
    build_pending_checklist_banner
)
from ..utils.logger import setup_logging

from .tasks import create_checklist_items, celery_app

# Initialize structured logging
logger = setup_logging(log_level=os.getenv("LOG_LEVEL", "INFO"))

# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("App startup: dependencies initialized via dependency injection")
    try:
        yield
    finally:
        logger.info("App execution terminated")

# Initialize FastAPI app
app = FastAPI(lifespan=lifespan)

# Include routers
from .routes.tasks import router as tasks_router
app.include_router(tasks_router)

# Helper functions (kept in main.py for now, can be moved later if needed)

# API Routes
@app.post("/chat/{session_id}")
async def chat_stream(
    session_id: str,
    request: AskRequest,
    router_graph_chat = Depends(get_router_graph_chat),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Streaming AI response(AI SDK Stream Protocol)"""

    # Generate correlation_id if not provided
    correlation_id = x_correlation_id or str(uuid.uuid4())

    async def generate() -> AsyncGenerator[str, None]:
        request_start_time = time.time()
        logger.info("Chat stream started", extra={
            "correlation_id": correlation_id,
            "session_id": session_id,
            "message_count": len(request.messages) if request.messages else 0
        })

        celery_monitor_task = None
        pending_task_id = None

        try:
            skip_generator_stream = False
            generator_skip_logged = False

            session, messages_for_agent = validate_messages(
                session_id,
                incoming_messages=request.messages
            )

            langchain_messages = convert_to_langchain_messages(messages_for_agent)
            graph_input = {"messages": langchain_messages}
            accumulated_content = ""  # Buffer to store complete response

            langraph_start_time = time.time()
            logger.info("LangGraph processing started", extra={
                "correlation_id": correlation_id,
                "session_id": session_id,
                "elapsed_ms": int((langraph_start_time - request_start_time) * 1000)
            })

            async for event in router_graph_chat.astream_events(
                graph_input,
                config={"configurable":{"thread_id": session_id}},
                version="v2"
            ):
                event_type = event["event"]

                # Identify which graph node produced this event (if available)
                node_name = event.get("name")
                if not node_name:
                    metadata = event.get("metadata") or {}
                    node_name = metadata.get("node") or metadata.get("langgraph_node")

                # Token-level streaming from LLM
                if event_type == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]

                    chunk_node = None
                    if hasattr(chunk, "response_metadata"):
                        chunk_node = chunk.response_metadata.get("langgraph_node")
                    if not chunk_node and hasattr(chunk, "message") and hasattr(chunk.message, "response_metadata"):
                        chunk_node = chunk.message.response_metadata.get("langgraph_node")

                    active_node = node_name or chunk_node

                    chunk_text = getattr(chunk, "content", "") or ""
                    stripped_text = chunk_text.strip()

                    if active_node in {"checklist_generator", "checklist_converter"} or stripped_text.startswith("{") or stripped_text.startswith('["') or '"title"' in chunk_text or '"summary"' in chunk_text:
                        skip_generator_stream = True
                        if not generator_skip_logged:
                            logger.debug("Checklist generation content detected, suppressing stream", extra={
                                "correlation_id": correlation_id,
                                "session_id": session_id
                            })
                            generator_skip_logged = True
                        continue

                    if skip_generator_stream:
                        continue

                    if chunk.content:
                        accumulated_content += chunk.content

                        logger.debug("Token streamed", extra={
                            "correlation_id": correlation_id,
                            "session_id": session_id,
                            "content_length": len(chunk.content)
                        })

                        yield "data:" + json.dumps({
                            'type': 'text-delta',
                            'delta': chunk.content
                        }) + "\n\n"
                        await asyncio.sleep(0)

                elif event_type == "on_node_end":
                    output_payload = (event.get("data") or {}).get("output") or {}

                    if node_name == "judge":
                        decision_payload = output_payload.get("agent_decision")
                        if decision_payload:
                            logger.debug("Judge decision payload ready", extra={
                                "correlation_id": correlation_id,
                                "session_id": session_id,
                                "action": decision_payload.get("action"),
                                "confidence": decision_payload.get("confidence")
                            })
                            yield "data:" + json.dumps({
                                'type': 'agent-decision',
                                'data': decision_payload
                            }) + "\n\n"

                    elif node_name == "price_search":
                        search_payload = output_payload.get("search_results")
                        if search_payload:
                            logger.debug("Search results payload ready", extra={
                                "correlation_id": correlation_id,
                                "session_id": session_id
                            })
                            yield "data:" + json.dumps({
                                'type': 'search-results',
                                'data': search_payload
                            }, ensure_ascii=False) + "\n\n"

                    elif node_name == "summary_agent":
                        price_summary = output_payload.get("price_summary")
                        summary_text = output_payload.get("conversation_summary")

                        if price_summary:
                            yield "data:" + json.dumps({
                                'type': 'price-summary',
                                'data': price_summary
                            }, ensure_ascii=False) + "\n\n"

                        if summary_text:
                            logger.debug("Summary text ready", extra={
                                "correlation_id": correlation_id,
                                "session_id": session_id,
                                "length": len(summary_text)
                            })
                            yield "data:" + json.dumps({
                                'type': 'text-delta',
                                'delta': summary_text
                            }) + "\n\n"
                            yield "data:" + json.dumps({
                                'type': 'text-complete',
                                'content': summary_text
                            }) + "\n\n"
                    elif node_name == "supervisor_agent":
                        supervisor_feedback = output_payload.get("supervisor_feedback")
                        supervisor_revision = output_payload.get("supervisor_revision")

                        if supervisor_revision:
                            # Prefer revised reply as final content delta
                            yield "data:" + json.dumps({
                                'type': 'text-delta',
                                'delta': supervisor_revision
                            }, ensure_ascii=False) + "\n\n"
                            yield "data:" + json.dumps({
                                'type': 'text-complete',
                                'content': supervisor_revision
                            }, ensure_ascii=False) + "\n\n"
                        elif supervisor_feedback:
                            # Surface supervisor notes for the client to optionally display
                            yield "data:" + json.dumps({
                                'type': 'supervisor-feedback',
                                'data': supervisor_feedback
                            }, ensure_ascii=False) + "\n\n"

                # Tool call detection
                elif event_type == "on_chat_model_end":
                    output = event["data"]["output"]

                    model_end_time = time.time()
                    print(f"[TIMING] LLM completed at: {model_end_time:.3f} (elapsed: {model_end_time - request_start_time:.3f}s)")
                    print(f"[DEBUG-END] LLM completed, checking for tool calls...")

                    # Check if there are tool calls
                    has_tool_calls = hasattr(output, 'tool_calls') and output.tool_calls

                    # Signal .NET to save text message - only if no tool calls
                    if not has_tool_calls:
                        if accumulated_content:
                            yield "data:" + json.dumps({
                                'type': 'text-complete',
                                'content': accumulated_content
                            }) + "\n\n"
                            print(f"[DEBUG-TEXT-COMPLETE] Sent text-complete signal with {len(accumulated_content)} chars")
                        else:
                            print(f"[DEBUG-TEXT-COMPLETE] Skipping text-complete signal - no content accumulated")
                    else:
                        print(f"[DEBUG-TEXT-COMPLETE] Skipping text-complete signal - tool call detected")

                    if has_tool_calls:
                        for tool_call in output.tool_calls:
                            tool_name = tool_call.get("name")
                            tool_id = tool_call.get("id")

                            logger.info("Tool call detected", extra={
                                "correlation_id": correlation_id,
                                "session_id": session_id,
                                "tool_name": tool_name,
                                "tool_id": tool_id
                            })

                            if tool_name == "trigger_checklist_generation":
                                tool_trigger_time = time.time()
                                logger.info("Checklist generation triggered", extra={
                                    "correlation_id": correlation_id,
                                    "session_id": session_id,
                                    "elapsed_ms": int((tool_trigger_time - request_start_time) * 1000)
                                })

                                try:
                                    task_id, stable_uuid = await submit_checklist_generation(
                                        create_checklist_items, session_id, messages_for_agent
                                    )

                                    celery_submit_time = time.time()
                                    logger.info("Celery task submitted", extra={
                                        "correlation_id": correlation_id,
                                        "session_id": session_id,
                                        "task_id": task_id,
                                        "stable_uuid": stable_uuid
                                    })
                                    pending_task_id = task_id

                                    yield "data:" + json.dumps({
                                        'type': 'task-id',
                                        'taskId': task_id,
                                        'status': 'pending'
                                    }) + "\n\n"

                                    yield "data:" + json.dumps({
                                        'type': 'data-checklist-pending',
                                        'data': {
                                            'taskId': task_id,
                                            'status': 'generating',
                                            'message': 'Generating your personalized checklist...'
                                        }
                                    }) + "\n\n"

                                    pending_banner_payload = build_pending_checklist_banner(session_id, task_id, stable_uuid)

                                    yield "data:" + json.dumps({
                                        'type': 'data-checklist-banner',
                                        'data': pending_banner_payload
                                    }) + "\n\n"

                                    banner_sent_time = time.time()
                                    logger.info("Checklist banner sent", extra={
                                        "correlation_id": correlation_id,
                                        "session_id": session_id,
                                        "task_id": task_id
                                    })

                                    celery_monitor_task = asyncio.create_task(
                                        wait_for_celery_result(celery_app, task_id)
                                    )

                                except Exception as checklist_error:
                                    logger.error("Checklist task submission failed", exc_info=True, extra={
                                        "correlation_id": correlation_id,
                                        "session_id": session_id
                                    })
                                    yield "data:" + json.dumps({
                                        'type': 'error',
                                        'error': f"Checklist task submission failed: {str(checklist_error)}"
                                    }) + "\n\n"

            # Wait for Celery result (if task triggered) and forward structured data
            if celery_monitor_task:
                wait_start_time = time.time()
                logger.info("Waiting for Celery task completion", extra={
                    "correlation_id": correlation_id,
                    "session_id": session_id,
                    "elapsed_ms": int((wait_start_time - request_start_time) * 1000)
                })

                monitor_result = await celery_monitor_task

                celery_complete_time = time.time()
                celery_duration_ms = int((celery_complete_time - celery_submit_time) * 1000)
                logger.info("Celery task completed", extra={
                    "correlation_id": correlation_id,
                    "session_id": session_id,
                    "total_elapsed_ms": int((celery_complete_time - request_start_time) * 1000),
                    "celery_duration_ms": celery_duration_ms
                })

                if monitor_result.get("status") == "completed" and monitor_result.get("result"):
                    checklist_payload = monitor_result["result"]
                    if isinstance(checklist_payload, str):
                        try:
                            checklist_payload = json.loads(checklist_payload)
                        except json.JSONDecodeError:
                            logger.warning("Checklist payload is string and failed to parse as JSON", extra={
                                "correlation_id": correlation_id,
                                "session_id": session_id
                            })
                    elif hasattr(checklist_payload, "model_dump"):
                        checklist_payload = checklist_payload.model_dump()

                    if isinstance(checklist_payload, dict) and checklist_payload.get("error"):
                        logger.error("Checklist generation returned error payload", extra={
                            "correlation_id": correlation_id,
                            "session_id": session_id,
                            "error": checklist_payload.get('error')
                        })
                        yield "data:" + json.dumps({
                            'type': 'data-checklist-error',
                            'data': {
                                'error': checklist_payload.get("error", "Checklist generation failed"),
                                'taskId': pending_task_id
                            }
                        }) + "\n\n"
                        return

                    logger.info("Checklist data ready to send", extra={
                        "correlation_id": correlation_id,
                        "session_id": session_id,
                        "checklist_id": checklist_payload.get('checklistId'),
                        "status": checklist_payload.get('status')
                    })

                    yield "data:" + json.dumps({
                        'type': 'data-checklist',
                        'data': checklist_payload
                    }) + "\n\n"

                    final_sent_time = time.time()
                    banner_to_final_ms = int((final_sent_time - banner_sent_time) * 1000)
                    logger.info("Final checklist sent", extra={
                        "correlation_id": correlation_id,
                        "session_id": session_id,
                        "total_elapsed_ms": int((final_sent_time - request_start_time) * 1000),
                        "banner_to_final_ms": banner_to_final_ms
                    })
                elif monitor_result.get("status") == "failed":
                    logger.error("Celery task failed", extra={
                        "correlation_id": correlation_id,
                        "session_id": session_id,
                        "error": monitor_result.get('error')
                    })
                    yield "data:" + json.dumps({
                        'type': 'data-checklist-error',
                        'data': {
                            'error': monitor_result.get('error', 'Checklist generation failed'),
                            'taskId': pending_task_id
                        }
                    }) + "\n\n"

        except Exception as e:
            logger.error("Chat stream failed", exc_info=True, extra={
                "correlation_id": correlation_id,
                "session_id": session_id
            })

            yield "data: " + json.dumps({
            'type': 'error',
            'error': str(e)
        }) + "\n\n"
            
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":"no-cache",
            "Connection":"keep-alive",
            "X-Accel-Buffering":"no",
        }
    )

@app.post("/generate-title")
async def generate_title(
    request: GenerateTitleRequest,
    llm: BaseChatModel = Depends(get_llm_chat)  # Use fast GPT-4o for title generation
) -> GenerateTitleResponse:
    """
    Generate conversation title based on user's first message

    Args:
        request: GenerateTitleRequest with message field

    Returns:
        GenerateTitleResponse with generated title
    """
    try:
        first_message = request.message

        # Generate title using LLM
        prompt = f"""Based on the user's message, generate a concise title of 10-20 characters.

    Requirements:
    1. Summarize the main topic without being too broad.
    2. Use the same language as the user's message (Chinese, English, etc.).
    3. Do not include quotation marks or special symbols.
    4. Return only the title, with no extra content.
    5. *CRITICAL* The title's language must match the user's message language (if the message is in English, return an English title; if in Chinese, return a Chinese title, etc.).

    User message: {first_message}

    Title: """

        logger.info("Generating conversation title", extra={
            "message_preview": first_message[:50]
        })

        # Use synchronous invoke for simpler error handling
        response = await llm.ainvoke(prompt)
        title = response.content.strip()

        # Remove quotes if LLM added them
        title = title.strip('"\'""''')

        # Ensure title length is appropriate
        if len(title) > 30:
            title = title[:27] + "..."

        logger.info("Title generated successfully", extra={
            "title": title
        })

        return GenerateTitleResponse(title=title)

    except Exception as e:
        logger.error("Failed to generate title", exc_info=True, extra={
            "message_preview": first_message[:50] if first_message else None
        })

        # Fallback: use first 20 characters of message
        fallback_title = first_message[:20] + "..." if len(first_message) > 20 else first_message

        return GenerateTitleResponse(title=fallback_title)
