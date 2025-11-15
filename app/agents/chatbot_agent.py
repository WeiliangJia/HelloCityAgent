from langchain.tools import tool
from langgraph.prebuilt import create_react_agent

from ..core.hooks import pre_model_hook, checkpointer
from ..utils.prompt_loader import load_prompt
from ..utils.tools import make_qa_tool

# Load prompt from external file for easy editing
HELLOCITY_ASK4_MESSAGE = load_prompt("chatbot")


@tool
def trigger_checklist_generation() -> str:
    """Call this tool ONLY when you have collected ALL required user information:
    - Destination (city AND country)
    - Timing (arrival date/window AND duration)

    Do NOT call this if any critical information is missing.
    """
    return "Checklist generation will be triggered"


def create_chatbot_agent(state):
    """Create a HelloCity chatbot agent - returns the inner react agent for graph compatibility."""
    tools = [trigger_checklist_generation]

    if getattr(state, "qa_chain", None) and getattr(state, "settings", None) and state.settings.enable_rag:
        tools.append(make_qa_tool(state.qa_chain))

    return create_react_agent(
        state.llm,
        tools,
        prompt=HELLOCITY_ASK4_MESSAGE,
        pre_model_hook=pre_model_hook,
        checkpointer=checkpointer,
    )
