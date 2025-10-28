from langgraph.prebuilt import create_react_agent
from ..core.hooks import checkpointer
from ..schemas.checklist_schema import GeneratedChecklist
from ..utils.tools import make_search_tool
from ..utils.prompt_loader import load_prompt

# Load prompt from external file for easy editing
CHECKLIST_GENERATOR_MESSAGE = load_prompt("checklist_generator")


def create_checklist_generator_agent(state):
    """Create backend agent that converts information to checklist responses"""
    print("[DEBUG-GENERATOR-AGENT] Creating checklist generator agent...")
    print(f"[DEBUG-GENERATOR-AGENT] LLM type: {type(state.llm).__name__}")

    search_tool = make_search_tool()
    print(f"[DEBUG-GENERATOR-AGENT] Tools: [{search_tool.name}]")

    # Pass base ChatOpenAI model directly to create_react_agent
    # Cannot use .bind(response_format=...) because:
    # 1. RunnableBinding doesn't have .bind_tools() method
    # 2. OpenAI doesn't allow json_schema + function_calling simultaneously
    # Structured output is enforced via prompt + wrapper validation
    agent = create_react_agent(
        state.llm,
        [search_tool],
        prompt=CHECKLIST_GENERATOR_MESSAGE,
        checkpointer=checkpointer
    )
    print("[DEBUG-GENERATOR-AGENT] ✅ Agent created successfully")
    return agent
