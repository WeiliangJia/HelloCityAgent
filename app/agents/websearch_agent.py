from langgraph.prebuilt import create_react_agent
from ..utils.tools import make_search_tool
from ..core.hooks import pre_model_hook, checkpointer
from ..utils.prompt_loader import load_prompt

# Load prompt from external file for easy editing
WEBSEARCH_CONFIDENCE_MESSAGE = load_prompt("websearch")

def create_websearch_agent(state):
    """Create a web search agent for finding current information"""
    search_tool = make_search_tool()
    return create_react_agent(
      state.llm,
      [search_tool],
      prompt=WEBSEARCH_CONFIDENCE_MESSAGE,
      pre_model_hook=pre_model_hook,
      checkpointer=checkpointer,
    )
    