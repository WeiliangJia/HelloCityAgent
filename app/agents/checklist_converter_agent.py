from langgraph.prebuilt import create_react_agent
from ..core.hooks import checkpointer
from ..models.schemas import ChecklistMetadata
from ..utils.prompt_loader import load_prompt

# Load prompt from external file for easy editing
METADATA_EXTRACTOR_MESSAGE = load_prompt("checklist_converter")

def create_checklist_converter_agent(state):
    """Create backend agent that converts checklist responses to structured JSON format"""
    return create_react_agent(
        state.llm,
        [],
        prompt=METADATA_EXTRACTOR_MESSAGE, 
        response_format=ChecklistMetadata,
        checkpointer=checkpointer
    )
