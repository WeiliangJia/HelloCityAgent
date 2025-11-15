
# HelloCity AI Service

A FastAPI-based AI service powered by LangChain and LangGraph, providing intelligent chat functionality with conversation memory, checklist generation, and SSE streaming for the HelloCity relocation assistant platform.

## 📋 Table of Contents

1. [Requirements](#1-requirements)
2. [Quick Start](#2-quick-start)
3. [Environment Configuration](#3-environment-configuration)
4. [API Endpoints](#4-api-endpoints)
5. [Key Features](#5-key-features)
6. [Tech Stack](#6-tech-stack)
7. [Development Commands](#7-development-commands)
8. [Integration with HelloCity Ecosystem](#8-integration-with-hellocity-ecosystem)
9. [Project Structure](#9-project-structure)
10. [Troubleshooting](#10-troubleshooting)
11. [Code Quality Standards](#11-code-quality-standards)

## 1. Requirements

- **Python**: 3.11 or higher
- **Docker Desktop**: 4.43.1 or higher (for Redis and containerized deployment)
- **OpenAI API Key**: Required for GPT model access
- **Operating System**: Windows, macOS, Linux

## 2. Quick Start

### Recommended: Local Development (Fastest)

1. **Create & activate virtual environment (recommended):**
   ```bash
   python -m venv .venv
   # macOS/Linux
   source .venv/bin/activate
   # Windows (PowerShell)
   .\.venv\Scripts\Activate
   pip install -r requirements.txt
   ```

2. **Create environment file:**
   ```bash
   cp .env.example .env.local
   # Edit .env.local with your OpenAI API key
   ```

3. **Start Redis (required for Celery):**
   ```bash
   docker compose up -d redis
   ```

4. **Start Celery worker:**
   ```bash
   celery -A app.api.tasks worker --loglevel=info --pool=solo
   ```

5. **Run development server:**
   ```bash
   uvicorn app.api.main:app --reload
   ```

6. **Access API:** http://localhost:8000

**Why Local Over Docker?**
- ✅ Faster hot-reload (no container rebuild)
- ✅ Better IDE integration
- ✅ Direct debugging support
- ✅ Native performance

### Alternative: Docker Compose

For isolated environment or if you don't have Python 3.11+:

```bash
docker compose up -d
```

This starts Redis, API server (port 8000), and Celery worker.

### Terminal Chat (CLI)

Use the bundled CLI tool for quick local conversations (including Tavily web search when `TAVILY_API_KEY` is present):

```bash
# Activate your virtualenv first, then run:
python cli_chat.py --stream
```

The script auto-loads `.env.local`; set either `OPENAI_API_KEY` or the Azure OpenAI variables plus `TAVILY_API_KEY` before running. For checklist generation and other background tasks, keep Redis + Celery running (`docker compose up redis` and `celery -A app.api.tasks worker --loglevel=info`). Use `/reset` to clear history or `/quit` to exit.

## 3. Environment Configuration

**Required:** Create `.env.local` file in the project root:

```bash
# macOS/Linux
cp .env.example .env.local

# Windows
copy .env.example .env.local
```

Populate `.env.local` with actual values:

```bash
# Required: OpenAI Configuration
OPENAI_API_KEY=sk-...

# Optional: Azure OpenAI (set all of these to route traffic through Azure)
AZURE_OPENAI_API_KEY=azure-...
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT=text-embedding-3-small

# Dual Model Strategy (recommended for cost/performance optimization)
LLM_MODEL_CHAT=gpt-4o-mini       # Fast model for conversation
LLM_MODEL_CHECKLIST=gpt-4o-mini  # High-quality model for checklist generation
LLM_MODEL=gpt-4o-mini            # Fallback for backward compatibility

# Required: Celery/Redis (auto-configured for Docker Compose)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Optional: Logging Level
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

### Important Configuration Notes

**Celery Task Result Expiration:**
- Task results are automatically deleted after **1 hour** (3600 seconds)
- Configured in `app/api/tasks.py`: `celery_app.conf.result_expires = 3600`
- Prevents Redis OOM by removing completed checklist generation results
- Frontend polls for max 5 minutes, so 1 hour provides ample buffer for page refreshes and network delays

**Dynamic Model Changes:**
- Simply edit `.env.local` and restart: `docker compose restart api celery`
- No caching ensures changes take effect immediately
- When Azure variables are present, the backend automatically instantiates `AzureChatOpenAI`/`AzureOpenAIEmbeddings`; omit them to keep calling `api.openai.com`

**Never commit `.env.local` to version control!**

## 4. API Endpoints

### Chat Streaming (Primary Endpoint)
**POST /chat/{session_id}**

Streams AI responses via Server-Sent Events (SSE). Accepts full conversation history and returns real-time streaming events.

**Request Body**:
```json
{
  "messages": [
    {"role": "user", "content": "I want to visit Sydney"},
    {"role": "assistant", "content": "Great choice! When are you planning to arrive?"},
    {"role": "user", "content": "Next month, for 5 days"}
  ]
}
```

**Response**: SSE stream with events:
- `text-delta` - Token chunks from AI
- `task-id` - Celery task ID for checklist generation
- `data-checklist-pending` - Checklist generation started
- `data-checklist-banner` - Temporary placeholder
- `data-checklist` - Final generated checklist
- `data-checklist-error` - Generation failed

### Title Generation
**POST /generate-title**

Generates a concise title for a conversation based on the first message.

**Request Body**:
```json
{
  "firstMessage": "I'm planning to move to Sydney for work"
}
```

**Response**:
```json
{
  "title": "Moving to Sydney for Work"
}
```

### Task Status
**GET /tasks/{task_id}**

Check the status of a background Celery task (e.g., checklist generation).

**Response**:
```json
{
  "task_id": "abc123",
  "status": "SUCCESS",
  "result": { ... }
}
```

## 5. Key Features

### Stateless Chat Architecture
- **Full History Per Request**: Client sends complete conversation history for scalability
- **No Server-Side Sessions**: Eliminates memory overhead and cache consistency issues
- **LangGraph Checkpointing**: `session_id` used only for threading, not persistence

### AI-Powered Checklist Generation
- **Automatic Detection**: Triggers when user info is complete
- **Background Processing**: Celery handles async generation without blocking chat
- **Structured Output**: Generates title, items, metadata (city, stay type, duration)
- **Dual-Stage Pipeline**: Generation → Metadata Extraction

### Multi-Agent Architecture
- **Chatbot Agent**: Conversational interviewer with tool calling
- **Checklist Generator**: Creates structured task lists
- **Checklist Converter**: Extracts metadata (city, dates, stay type)
- **Web Search Agent**: Confidence-based retry mechanism with Tavily integration
- **LangGraph Orchestration**: State machine routes between agents (recursion_limit=50)

### Token-Level Streaming
- **Real-Time SSE**: Server-Sent Events for smooth UX
- **Message Trimming**: Automatic 16k token limit management
- **Dual Model Strategy**: Fast model for chat (gpt-4o-mini), high-quality for checklists

### Hot-Reload Configuration
- **No Caching**: All dependencies created without `@lru_cache`
- **Dynamic Model Changes**: Edit `.env.local` and restart services
- **Dependency Injection**: Type-safe providers via FastAPI `Depends()`

## 6. Tech Stack

### Core Framework
- [FastAPI](https://fastapi.tiangolo.com/) - Async web framework with SSE streaming
- [Python 3.11+](https://www.python.org/) - Programming language

### AI & LLM
- [LangChain](https://python.langchain.com/) - LLM framework with tool support
- [LangGraph](https://langchain-ai.github.io/langgraph/) - Multi-agent state machine orchestration
- [OpenAI](https://openai.com/) - GPT model provider (gpt-4o-mini, gpt-5-chat)
- [Pydantic](https://docs.pydantic.dev/) - Data validation and settings management

### Background Processing
- [Celery](https://docs.celeryq.dev/) - Distributed task queue
- [Redis](https://redis.io/) - Message broker for Celery

### Vector Store & Search
- [ChromaDB](https://www.trychroma.com/) - Embedding storage for RAG
- [Tavily](https://tavily.com/) - Web search API integration

### Development Tools
- [uvicorn](https://www.uvicorn.org/) - ASGI server for FastAPI
- [python-dotenv](https://github.com/theskumar/python-dotenv) - Environment variable management

## 7. Development Commands

### Start Services

```bash
# Start all services (Docker)
docker compose up -d

# Start Redis only (for local Python dev)
docker compose up -d redis

# Start API server (local)
uvicorn app.main:app --reload

# Start Celery worker (local)
celery -A app.api.tasks worker --loglevel=info --pool=solo
```

### View Logs

```bash
# View API logs
docker compose logs -f api

# View Celery logs
docker compose logs -f celery

# View Redis logs
docker compose logs -f redis

# View streaming debug logs
docker compose logs -f api | grep -E "DEBUG-TOKEN|DEBUG-TOOL|DEBUG-LLM"
```

### Restart Services

```bash
# Restart API only
docker compose restart api

# Restart Celery only
docker compose restart celery

# Restart all services
docker compose restart
```

### Stop Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes
docker compose down -v
```

## 8. Integration with HelloCity Ecosystem

### Service Communication Flow
```
Frontend (Next.js)
  ↓ POST /api/chat (full conversation history)
.NET Backend (ChatProxyController)
  ↓ POST /chat/{conversationId} (SSE proxy)
Python AI Service (FastAPI + LangGraph)
  ↓ OpenAI API (streaming)
  ↓ LangChain tool: trigger_checklist_generation
  ↓ Celery background task (15-30s)
  ↓ SSE: data-checklist event
.NET Backend (ChecklistService)
  ↓ Parse and persist to PostgreSQL
Frontend
  ↓ Display completed checklist
```

### Data Flow
1. Frontend sends complete conversation history to .NET backend
2. .NET validates Auth0 JWT, forwards to Python AI service
3. Python converts dict messages → LangChain objects → LangGraph → OpenAI
4. OpenAI streams tokens back through Python → .NET → Frontend
5. Python AI detects user info completeness, triggers checklist generation tool
6. Celery task generates structured checklist asynchronously (stored in Redis for 1 hour)
7. Python emits `data-checklist` SSE event with full payload
8. .NET parses payload, persists to PostgreSQL (permanent storage)
9. Frontend polls Celery task status (max 5 minutes), displays checklist when complete

### Message Format Agreement
- **Input**: `{"messages": [{"role": "user", "content": "..."}]}`
- **Output**: SSE events with camelCase JSON (matches .NET global serialization)
- **LangChain Conversion**: Dicts → `HumanMessage`/`AIMessage` objects required for LangGraph

## 9. Project Structure

```
app/
├── api/                        # API Layer
│   ├── main.py                 # FastAPI app entry point
│   ├── tasks.py                # Celery task definitions
│   └── routes/                 # Additional route modules
├── services/                   # Service Layer (NEW)
│   ├── message_service.py      # Message validation & conversion
│   └── checklist_service.py    # Checklist business logic
├── core/                       # Core Layer
│   ├── graph.py                # LangGraph router with singleton
│   └── hooks.py                # Pre-model hooks (message trimming)
├── agents/                     # Domain Layer
│   ├── chatbot_agent.py        # Conversational interviewer
│   ├── checklist_generator_agent.py    # Checklist creation
│   ├── checklist_converter_agent.py    # Metadata extraction
│   └── websearch_agent.py      # Web search integration
├── config/                     # Configuration Layer (NEW)
│   ├── settings.py             # Pydantic Settings
│   └── dependencies.py         # Dependency injection providers
├── schemas/                    # Pydantic Models
│   ├── checklist_schema.py     # Checklist schemas
│   └── chat_schema.py          # Chat request/response
└── utils/                      # Helper Utilities
```

### Architecture Highlights
- **Layered Architecture**: Clean separation of concerns (API → Service → Core → Domain)
- **Stateless Design**: No server-side session caching, client sends full history
- **Dual Model Strategy**: Separate models for chat (fast) and checklist (high-quality)
- **Hot-Reload Config**: No caching allows dynamic model changes via `.env.local`
- **Dependency Injection**: Type-safe providers for LLM, vectorstore, graphs
- **Service Layer Pattern**: Business logic separated from HTTP concerns
- **Message Trimming**: Automatic token management (16k token limit) before LLM calls

## 10. Troubleshooting

### Issue: AI responses lose context
**Solution**: Ensure .NET backend sends full conversation history in `messages[]` array, not just last message. Architecture is stateless by design.

### Issue: Messages not reaching OpenAI
**Solutions**:
1. Check `app/services/message_service.py` - Verify `convert_to_langchain_messages()` is called
2. Check `app/core/hooks.py` - Ensure `pre_model_hook` isn't trimming all messages (max 16k tokens)
3. Verify LangChain message objects created correctly (`HumanMessage`/`AIMessage`, not dicts)

### Issue: Tool calls triggering prematurely
**Solution**: Review chatbot agent prompt in `app/agents/chatbot_agent.py`. Strengthen "DO NOT CALL" conditions.

### Issue: Dependency injection not working
**Solutions**:
1. Check `app/config/settings.py` - Ensure `.env.local` exists with required vars
2. Verify dependency functions are properly defined in `app/config/dependencies.py`
3. Use `Depends(get_dependency)` in FastAPI route parameters
4. Restart containers to pick up `.env.local` changes: `docker compose restart api celery`

### Issue: Redis memory growing indefinitely
**Solution**: Already fixed! `celery_app.conf.result_expires = 3600` in `app/api/tasks.py` auto-deletes task results after 1 hour.

### Issue: Model changes not taking effect
**Solutions**:
1. Edit `.env.local` with new model names
2. Restart containers: `docker compose restart api celery`
3. Verify in logs: `docker compose logs api celery | grep "DEBUG-LLM"`
4. No code changes needed - hot-reload is enabled

## 11. Code Quality Standards

### Service Layer Pattern
- Business logic MUST be in `app/services/`, not `app/api/main.py`
- API layer handles HTTP concerns only (request/response)
- Services return domain objects, not HTTP responses

### Dependency Injection
- Use `Depends()` to inject into FastAPI routes
- No caching for hot-reload capability (removed all `@lru_cache`)
- Never use global variables or `app.state` for dependencies
- Always use Pydantic Settings for configuration

### Function Size & Responsibility
- Keep functions under 50 lines
- Extract nested functions to module level
- One function = one responsibility

### Configuration Management
- Use Pydantic Settings for all env vars
- Never hardcode model names, API keys, or URLs
- Support dynamic changes without code deployment

## Example Usage

### Stateless Chat Flow
```bash
# 1) Start conversation (no session history)
curl -X POST "http://localhost:8000/chat/session-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "I want to visit Sydney"}
    ]
  }'

# 2) Continue conversation (send full history)
curl -X POST "http://localhost:8000/chat/session-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "I want to visit Sydney"},
      {"role": "assistant", "content": "Great! When are you planning to arrive?"},
      {"role": "user", "content": "Next month for 5 days"}
    ]
  }'

# 3) Provide all details to trigger checklist generation
curl -X POST "http://localhost:8000/chat/session-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "I want to visit Sydney"},
      {"role": "assistant", "content": "Great! When are you planning to arrive?"},
      {"role": "user", "content": "Next month for 5 days. Just me, budget-friendly, interested in public transport and iconic sights"},
      {"role": "assistant", "content": "Perfect! I have all the details. Let me confirm: ..."},
      {"role": "user", "content": "Yes, please create the checklist"}
    ]
  }'
```

**Note**:
- The service is **stateless** - always send the complete conversation history
- `session_id` is used only for LangGraph checkpointer threading
- Backend (.NET) automatically stores messages in PostgreSQL

### Generate Conversation Title
```bash
curl -X POST "http://localhost:8000/generate-title" \
  -H "Content-Type: application/json" \
  -d '{
    "firstMessage": "I am planning to relocate to Melbourne for a new job"
  }'
```

### Check Task Status
```bash
curl -X GET "http://localhost:8000/tasks/abc-123-def-456"
```

## Project Status

**Last Updated**: 2025-01-14

**Recent Improvements**:
- ✅ Stateless architecture (removed server-side session caching)
- ✅ Dual model strategy (separate models for chat vs checklist)
- ✅ Hot-reload configuration (removed all caching for dynamic model changes)
- ✅ Websearch agent with confidence-based retry mechanism (recursion_limit=50)
- ✅ Dependency injection refactoring (`app.state` → dependency providers)
- ✅ Service layer extraction (business logic separated from HTTP)
- ✅ Function decomposition (reduced complexity)
- ✅ Structured output for checklists (`with_structured_output()`)
- ✅ Async task streaming with `task-id` SSE events
- ✅ Celery result expiration (1 hour TTL to prevent Redis OOM)

**See CLAUDE.md** for detailed architecture documentation and integration guides.

---

For questions or issues, please contact the development team or file an issue in the project repository.
