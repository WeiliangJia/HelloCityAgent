# Prompts Directory

This directory contains all system prompts used by HelloCity AI Service agents.

## Files

- `chatbot.txt` - Conversational interviewer that collects user travel information
- `checklist_generator.txt` - Generates structured JSON checklists
- `checklist_converter.txt` - Extracts metadata from checklists
- `websearch.txt` - Web search agent with confidence evaluation

## Usage

Prompts are loaded dynamically via `app/utils/prompt_loader.py`:

```python
from app.utils.prompt_loader import load_prompt

CHATBOT_PROMPT = load_prompt("chatbot")
```

## Editing Guidelines

1. **Direct editing**: Simply edit the `.txt` files - changes take effect on next container restart
2. **No code changes needed**: The loader automatically picks up new content
3. **Hot reload**: For local development with `uvicorn --reload`, changes apply immediately
4. **Docker**: Restart containers with `docker compose restart api celery`

## Testing Changes

After modifying prompts:

```bash
# Local development (instant)
# Just save the file - uvicorn --reload picks it up

# Docker development
docker compose restart api celery
docker compose logs -f api | grep -E "DEBUG-TOKEN|DEBUG-TOOL"
```

## Translation Reference

For Chinese translations and detailed explanations, see `PROMPTS.md` in the project root.

## Best Practices

1. **Keep it concise**: Shorter prompts = faster processing + lower costs
2. **Be explicit**: Clear instructions reduce hallucinations
3. **Test thoroughly**: Always test with real conversations
4. **Version control**: Use meaningful commit messages when changing prompts
5. **Document changes**: Update `PROMPTS.md` if you add major changes

## Architecture Notes

- **Stateless**: Client sends full conversation history, no server-side caching
- **Tool calling**: `chatbot.txt` prompt must coordinate with `trigger_checklist_generation` tool
- **JSON output**: `checklist_generator.txt` must produce valid, parseable JSON
- **Confidence scoring**: `websearch.txt` must end with `CONFIDENCE_SCORE: X.X` format
