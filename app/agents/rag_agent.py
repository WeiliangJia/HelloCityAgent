from langgraph.prebuilt import create_react_agent
from ..utils.tools import make_qa_tool
from ..core.hooks import pre_model_hook, checkpointer

def create_rag_agent(state):
    """Create a RAG agent with QA tool for document retrieval"""
    qa_tool = make_qa_tool(state.qa_chain)
    return create_react_agent(
      state.llm,
      [qa_tool],
      pre_model_hook=pre_model_hook,
      checkpointer=checkpointer
    )