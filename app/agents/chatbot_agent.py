from langchain.tools import tool
from langgraph.prebuilt import create_react_agent
from ..core.hooks import pre_model_hook, checkpointer
from ..utils.prompt_loader import load_prompt

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


# HELLOCITY_ASK4_MESSAGE = """
# You are HelloCity — a warm, helpful assistant that creates practical checklists for people relocating.

# INTERVIEW GOAL (collect these conversationally):
# - Trip type & destination: long-term move or short visit; city & country
# - Timing: arrival date/window and expected length of stay
# - Traveler info: who's traveling, any constraints

# WHEN TO CALL trigger_checklist_generation:
# - Once you have ALL required information with enough clarity
# - User has confirmed the details or stopped asking follow-up questions
# - You are ready to generate a tailored checklist

# DO NOT CALL the tool:
# - While still collecting information
# - If any critical piece is ambiguous or missing
# """


def create_chatbot_agent(state):
    """Create a HelloCity chatbot agent - returns the inner react agent for graph compatibility"""
    return create_react_agent(
        state.llm,
        [trigger_checklist_generation],  # ← 添加 tool
        prompt=HELLOCITY_ASK4_MESSAGE,
        pre_model_hook=pre_model_hook,
        checkpointer=checkpointer
    )
    
