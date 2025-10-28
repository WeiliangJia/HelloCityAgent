# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HelloCity AI Service is a FastAPI-based Python backend powered by LangChain and LangGraph. It provides AI-powered chat functionality with conversation memory, RAG capabilities, web search, and checklist generation for travel/relocation planning.

## Development Commands

### 🚀 Recommended: Local Development (for faster hot-reload)

If you have Python 3.11+ installed locally:

- **Install dependencies**: `pip install -r requirements.txt`
- **Run development server**: `uvicorn app.main:app --reload` (runs on http://localhost:8000)
- **Run with specific host/port**: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

**Why Local Over Docker?**
- ✅ **Faster hot-reload** - No container rebuild needed
- ✅ **Better IDE integration** - Direct debugging support
- ✅ **Native performance** - No Docker overhead

### Docker Development (alternative for isolated environment)

Use Docker Compose only if:
- You don't have Python 3.11+ environment setup
- You need Redis/Celery running together
- You prefer completely isolated environment

**Commands:**
- **Start all services**: `docker compose up` (from project root)
- **Restart API only**: `docker compose restart api`
- **View logs**: `docker compose logs --tail=100 api`
- **Stop all services**: `docker compose down`

**Docker Services:**
- `api` - FastAPI app (port 8000)
- `celery` - Background task worker
- `redis` - Message broker for Celery

## Architecture

### Layered Architecture (Clean Architecture Pattern)

**API Layer** (`app/api/`)
- `main.py` - FastAPI endpoints and HTTP routing only
- `tasks.py` - Celery task definitions
- `routes/` - Additional route modules

**Service Layer** (`app/services/`) **[NEW]**
- `message_service.py` - Message validation and conversion
- `checklist_service.py` - Checklist generation business logic
- Encapsulates business logic, isolated from HTTP layer

**Configuration Layer** (`app/config/`) **[NEW]**
- `settings.py` - Pydantic Settings for type-safe configuration with dual model strategy
- `dependencies.py` - Dependency injection providers (no caching for hot-reload capability)

**Core Layer** (`app/core/`)
- `graph.py` - LangGraph orchestration with singleton pattern
- `hooks.py` - Pre-model hooks (message trimming, checkpointer)

**Domain Layer**
- `app/models/schemas.py` - Pydantic models (AskRequest, RouterState)
- `app/agents/` - LangChain agent definitions
  - `chatbot_agent.py` - Conversational interviewer with tool calling
  - `websearch_agent.py` - Web search integration
  - `checklist_generator_agent.py` - Structured checklist creation
  - `checklist_converter_agent.py` - Metadata extraction
- `app/utils/` - Helper utilities

### Key Technologies
- **FastAPI**: Async web framework with SSE streaming
- **Pydantic Settings**: Type-safe configuration management **[NEW]**
- **LangChain**: LLM framework with OpenAI integration
- **LangGraph**: State machine for multi-agent orchestration
- **Celery**: Distributed task queue with Redis broker
- **ChromaDB**: Vector database for RAG
- **OpenAI**: GPT model provider (via `LLM_MODEL` env var)

### Architecture Improvements (Recent Refactoring)

**Phase 1: Stateless Architecture**
- Removed server-side session caching
- Client sends full conversation history via `messages[]` array
- Simplified from dual-mode to single stateless mode

**Phase 2: Dependency Injection & Hot-Reload Config**
- Replaced `app.state` with dependency providers in `app/config/dependencies.py`
- Created `app/config/settings.py` with Pydantic Settings
- Removed all `@lru_cache` decorators for hot-reload capability
- All dependencies injected via FastAPI `Depends()`

**Phase 3: Service Layer Extraction**
- Moved business logic from `main.py` to `app/services/`
- API layer now focused on HTTP concerns only
- Improved testability and separation of concerns

**Phase 4: Function Decomposition**
- Extracted helper functions from nested scopes
- Reduced `chat_stream` from ~300 lines to ~250 lines
- Functions now independently testable

**Phase 5: Dual Model Strategy & Websearch Optimization**
- Separate models for chat (`LLM_MODEL_CHAT`) and checklist (`LLM_MODEL_CHECKLIST`)
- Websearch agent with confidence-based retry mechanism
- Increased recursion limit to 50 for nested agent support
- Backward compatibility via `@model_validator` fallback logic

## Chat Streaming Architecture

### Message Flow (.NET → Python → OpenAI)

**Endpoint**: `POST /chat/{session_id}`

**1. Message Reception (main.py:144-173)**
```python
# Receives full conversation history from .NET
{
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}

# Converts dict messages to LangChain objects
langchain_messages = [
  HumanMessage(content="..."),
  AIMessage(content="...")
]
```

**2. LangGraph Processing (main.py:175-182)**
```python
graph_input = {"messages": langchain_messages}

async for event in app.state.router_graph.astream_events(
    graph_input,
    config={"configurable": {"thread_id": session_id}},
    version="v2"
):
    # Token-level streaming via astream_events v2
```

**3. Token Streaming (main.py:185-203)**
```python
# Event: on_chat_model_stream
if chunk.content:
    yield "data:" + json.dumps({
        'type': 'text-delta',
        'delta': chunk.content
    }) + "\n\n"
```

**4. Tool Call Detection (main.py:205-240)**
```python
# Event: on_chat_model_end
if output.tool_calls:
    # Trigger Celery background tasks
    task = create_checklist_items.delay(session_id, messages_for_agent)

    # Send tool events to frontend
    yield tool-call event
    yield tool-output-available event
```

### Message Trimming (hooks.py:4-14)
```python
def pre_model_hook(state):
    trimmed_messages = trim_messages(
        state["messages"],
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=16000,
        start_on="human",
        end_on=("human", "tool"),
    )
    return {"llm_input_messages": trimmed_messages}
```

**Key Points:**
- Keeps last 16k tokens of conversation history
- Ensures messages start with `HumanMessage` and end with `HumanMessage` or `ToolMessage`
- Applied before every LLM call via LangGraph's pre-model hook

### Session Management

**Stateless Architecture:**
- No server-side session storage
- Client sends complete conversation history via `messages[]` array in every request
- `session_id` used only for LangGraph checkpointer threading

```python
# services/message_service.py
def validate_messages(session_id: str, incoming_messages: list) -> tuple[None, list]:
    """Parse and validate incoming messages"""
    if not incoming_messages:
        raise ValueError("messages array is required")

    # Validation and logging only, no caching
    return None, incoming_messages
```

**Benefits:**
- Scalable: No memory overhead per session
- Reliable: No risk of cache inconsistency
- Simple: Single code path, no dual-mode complexity

### LangGraph State Machine

**Router Graph** (core/graph.py):
- Routes between chatbot, RAG, and websearch agents based on query type
- Maintains conversation state across agent transitions
- Uses `InMemorySaver` checkpointer for persistence

**Agent Tools:**
- `trigger_checklist_generation` - Called by chatbot when user info is complete
- Triggers Celery background task for async checklist generation

## API Endpoints

### Chat Streaming
**POST /chat/{session_id}**
- **Input**: `AskRequest` with `messages[]` (full conversation history)
- **Output**: SSE stream with AI SDK protocol events
- **Events**:
  - `text-delta` - Token chunks from LLM
  - `task-id` - Celery task submitted for checklist generation
  - `data-checklist-pending` - Checklist generation started
  - `data-checklist-banner` - Temporary checklist placeholder
  - `data-checklist` - Final generated checklist
  - `data-checklist-error` - Checklist generation failed

**Service Layer Flow:**
1. `validate_messages()` - Validate incoming messages
2. `convert_to_langchain_messages()` - Convert to LangChain format
3. LangGraph streaming - Process through agent graph
4. `submit_checklist_generation()` - Submit Celery task if tool called
5. `wait_for_celery_result()` - Poll for task completion

### Title Generation
**POST /generate-title**
- **Input**: `GenerateTitleRequest` with first message
- **Output**: `GenerateTitleResponse` with generated title
- Uses injected LLM via `Depends(get_llm)`

### Task Status (API Routes)
**GET /tasks/{task_id}**
- **Output**: Celery task status and result
- See `app/api/routes/tasks.py`

## Environment Setup

**Required Environment Variables** (`.env.local`):
```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-...

# Dual Model Strategy (recommended for cost/performance optimization)
LLM_MODEL_CHAT=gpt-4o-mini  # Fast model for conversation
LLM_MODEL_CHECKLIST=gpt-4o-mini  # High-quality model for checklist generation
LLM_MODEL=gpt-4o-mini  # Fallback for backward compatibility

# Celery/Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

**Dynamic Model Changes:**
- No caching: Simply edit `.env.local` and restart containers
- Restart command: `docker compose restart api celery`
- Check active models: `docker compose logs api celery | grep "DEBUG-LLM"`

**Docker Compose** automatically sets these for containerized deployment.

## Integration with HelloCity Ecosystem

**Service Communication:**
```
Frontend (Next.js)
  ↓ POST /api/chat (full history)
.NET Backend (ChatProxyController)
  ↓ POST /chat/{conversationId} (SSE proxy)
Python AI Service (FastAPI + LangGraph)
  ↓ OpenAI API (streaming)
```

**Data Flow:**
1. Frontend sends complete conversation history to .NET
2. .NET validates auth, forwards to Python
3. Python converts dicts → LangChain messages → LangGraph → OpenAI
4. OpenAI streams tokens back through Python → .NET → Frontend
5. .NET saves final messages to PostgreSQL

## Key Implementation Details

### Message Format Conversion
**Critical**: Must convert dict messages to LangChain objects before LangGraph:
```python
# ❌ Wrong (causes 0 messages sent to OpenAI)
graph_input = {"messages": [{"role": "user", "content": "..."}]}

# ✅ Correct (handled by service layer)
from app.services.message_service import convert_to_langchain_messages

langchain_messages = convert_to_langchain_messages(messages)
graph_input = {"messages": langchain_messages}
```

**Reason**: LangGraph's `trim_messages` expects `HumanMessage`/`AIMessage` instances, not dicts.

### Dependency Injection Pattern
```python
# config/dependencies.py
def get_llm_chat() -> ChatOpenAI:
    """Fast LLM for conversation (no caching for hot-reload)"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating ChatOpenAI (chat) with model: {settings.llm_model_chat}")
    return ChatOpenAI(model=settings.llm_model_chat, streaming=True)

def get_llm_checklist() -> ChatOpenAI:
    """High-quality LLM for checklist generation (no caching for hot-reload)"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating ChatOpenAI (checklist) with model: {settings.llm_model_checklist}")
    return ChatOpenAI(model=settings.llm_model_checklist, streaming=True)

# api/main.py
@app.post("/generate-title")
async def generate_title(
    request: GenerateTitleRequest,
    llm: ChatOpenAI = Depends(get_llm_chat)  # ← Injected dependency
):
    response = await llm.ainvoke(prompt)
```

**Benefits:**
- Type-safe: FastAPI validates dependency types
- Testable: Easy to mock `get_llm_chat()` in tests
- Hot-reload: No caching allows dynamic model changes via `.env.local`
- Dual models: Separate chat and checklist LLM instances

### Streaming Performance
- Uses `asyncio.sleep(0)` between chunks for event loop yielding
- SSE format: `data: {...}\n\n` (double newline required)
- Frontend adds 10ms delay to prevent browser batching

### Celery Background Tasks
**Checklist Generation** (api/tasks.py):
- Triggered via service layer: `submit_checklist_generation()`
- Runs asynchronously, doesn't block chat stream
- Uses `get_router_graph_generate()` and `get_router_graph_convert()`
- Monitored via `wait_for_celery_result()` polling

## Testing & Debugging

**View Streaming Logs:**
```bash
docker compose logs -f api | grep -E "DEBUG-TOKEN|DEBUG-TOOL|DEBUG-END"
```

**Test Endpoint:**
```bash
curl -X POST http://localhost:8000/chat/test-session \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

## Known Issues & Solutions

### Issue: AI responses lose context
**Solution**: Ensure frontend sends full conversation history in `messages[]` array, not just last message. Architecture is now stateless by design.

### Issue: Messages not reaching OpenAI
**Solution**:
1. Check `services/message_service.py` - Verify `convert_to_langchain_messages()` is called
2. Check `core/hooks.py` - Ensure `pre_model_hook` isn't trimming all messages (max_tokens=16000)
3. Verify LangChain message objects created correctly (HumanMessage/AIMessage, not dicts)

### Issue: Tool calls triggering prematurely
**Solution**: Review chatbot agent prompt in `agents/chatbot_agent.py`. Strengthen "DO NOT CALL" conditions.

### Issue: Dependency injection not working
**Solution**:
1. Check `config/settings.py` - Ensure `.env.local` exists and contains required vars
2. Verify dependency functions are properly defined in `config/dependencies.py`
3. Use `Depends(get_dependency)` in FastAPI route parameters
4. Restart containers to pick up `.env.local` changes: `docker compose restart api celery`

### Issue: Model changes not taking effect
**Solution**:
1. Edit `.env.local` with new model names
2. Restart containers: `docker compose restart api celery`
3. Verify in logs: `docker compose logs api celery | grep "DEBUG-LLM"`
4. No code changes needed - hot-reload is enabled

## Code Quality Standards

### Service Layer Pattern
- Business logic MUST be in `app/services/`, not `app/api/main.py`
- API layer handles HTTP concerns only (request/response)
- Services return domain objects, not HTTP responses

### Dependency Injection
- Use `Depends()` to inject into FastAPI routes
- No caching for hot-reload capability (removed all `@lru_cache`)
- Never use global variables or `app.state` for dependencies
- Always use Pydantic Settings for configuration

### Function Size
- Keep functions under 50 lines
- Extract nested functions to module level
- One function = one responsibility
