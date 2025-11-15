"""Message handling and conversion service"""
from langchain_core.messages import HumanMessage, AIMessage


def validate_messages(session_id: str, incoming_messages: list) -> tuple[None, list]:
    """Parse and validate incoming messages

    Returns:
        tuple: (session, messages) - session is always None for stateless mode
    """
    if not incoming_messages:
        raise ValueError("messages array is required")

    print(f"[INFO] Processing {len(incoming_messages)} messages for session {session_id}")
    for i, msg in enumerate(incoming_messages):
        content = msg.get("content", "")
        content_length = len(content) if content else 0
        print(f"[DEBUG] Message {i}: role={msg.get('role')}, length={content_length}, content={content or '[EMPTY]'}")

    return None, incoming_messages


def convert_to_langchain_messages(messages: list) -> list:
    """Convert dict messages to LangChain message objects"""
    langchain_messages = []
    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')

        if role == 'user':
            langchain_messages.append(HumanMessage(content=content))
        elif role == 'assistant':
            langchain_messages.append(AIMessage(content=content))
    return langchain_messages


def prepare_messages_for_celery(messages: list) -> list:
    """Convert messages to Celery-serializable format"""
    return [
        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
        for msg in messages
    ]
