"""Shared conversation utilities for determining conversation state."""

def is_conversation_ready_for_processing(content: str) -> bool:
    """
    Check if the conversation content indicates readiness to proceed to processing.

    Args:
        content: The message content to analyze

    Returns:
        bool: True if ready to proceed to processing, False if still collecting info
        
    We can also just replace this with a llm
    """
    # Check if chatbot is still asking questions
    if "?" in content:
        # Check for keywords that indicate completion (summary confirmation)
        completion_keywords = ["summary", "confirm", "bullet points", "proceed", "generate"]
        if any(keyword in content.lower() for keyword in completion_keywords):
            return True  # Ready to proceed to processing
        return False  # Still collecting info

    # If no question mark, assume ready to proceed
    return True