from langgraph.graph import StateGraph, START, END
from ..models.schemas import RouterState
from .hooks import checkpointer
from ..agents import create_chatbot_agent, create_websearch_agent, create_checklist_generator_agent, create_checklist_converter_agent
from ..config.dependencies import get_llm, get_llm_chat, get_llm_checklist, get_qa_chain
from ..utils.logger import setup_logging
import os
import re
import json

# Initialize logger
logger = setup_logging(log_level=os.getenv("LOG_LEVEL", "INFO"))


def websearch_wrapper(agent):
    """Wrapper to extract confidence score from websearch agent response with graceful degradation."""

    def websearch_node(state):
        logger.debug("Websearch agent started")

        try:
            # Call with recursion limit to prevent infinite loops
            result = agent.invoke(
                state,
                config={"recursion_limit": 50}
            )

            confidence = 0.7  # Optimistic default
            if result.get("messages"):
                last_message = result["messages"][-1]
                content = last_message.content if hasattr(last_message, "content") else str(last_message)
                confidence_match = re.search(r"CONFIDENCE_SCORE:\s*([0-9]*\.?[0-9]+)", content)
                if confidence_match:
                    confidence = float(confidence_match.group(1))
                    logger.info("Websearch completed successfully", extra={
                        "confidence": confidence
                    })

            return {
                "messages": result.get("messages", []),
                "websearch_confidence": confidence,
            }

        except Exception as e:
            # Graceful degradation: Continue workflow even if websearch fails
            logger.warning(f"Websearch failed: {type(e).__name__}: {str(e)[:100]}")
            logger.info("Continuing with fallback - checklist will be generated without web search")

            return {
                "messages": state.get("messages", []),
                "websearch_confidence": 0.7,  # High confidence to proceed
            }

    return websearch_node


def checklist_generation_wrapper(agent):
    """Wrapper that ensures generated checklist JSON is captured and validated from agent output."""
    from ..schemas.checklist_schema import GeneratedChecklist
    from pydantic import ValidationError

    def generator_node(state):
        logger.debug("Checklist generator started")

        result = agent.invoke(state)

        generated_checklist = None
        raw_data = None

        # Extract raw data from agent output
        if isinstance(result, dict) and result.get("structured_response"):
            structured_resp = result["structured_response"]
            if hasattr(structured_resp, "model_dump"):
                raw_data = structured_resp.model_dump()
            elif isinstance(structured_resp, dict):
                raw_data = structured_resp

        if not raw_data and result.get("messages"):
            for message in reversed(result["messages"]):
                content = getattr(message, "content", None)

                if hasattr(content, "model_dump"):
                    try:
                        raw_data = content.model_dump()
                        break
                    except Exception:
                        continue
                if isinstance(content, dict) and content.get("items"):
                    raw_data = content
                    break
                if isinstance(content, str):
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict) and parsed.get("items"):
                            raw_data = parsed
                            break
                    except json.JSONDecodeError:
                        continue

        # Validate against Pydantic schema
        if raw_data:
            try:
                validated_model = GeneratedChecklist.model_validate(raw_data)
                generated_checklist = validated_model.model_dump()
                logger.info("Checklist generation successful", extra={
                    "items_count": len(generated_checklist.get('items', []))
                })
            except ValidationError as e:
                logger.warning("Schema validation failed, attempting fallback", extra={
                    "error_count": e.error_count()
                })

                # Fallback: Use with_structured_output to fix the data
                try:
                    structured_llm = get_llm().with_structured_output(GeneratedChecklist)
                    last_message = result.get("messages", [])[-1] if result.get("messages") else None
                    if last_message:
                        correction_prompt = f"Fix this checklist to match the schema:\n{json.dumps(raw_data, indent=2)}"
                        fixed_model = structured_llm.invoke(correction_prompt)
                        generated_checklist = fixed_model.model_dump() if hasattr(fixed_model, "model_dump") else fixed_model
                        logger.info("Fallback correction successful")
                    else:
                        generated_checklist = raw_data
                except Exception as fallback_error:
                    logger.error("Fallback correction failed", exc_info=True)
                    generated_checklist = raw_data
        else:
            logger.warning("No raw_data extracted from agent output")

        if not generated_checklist:
            logger.error("Failed to generate checklist")

        return {
            "messages": result.get("messages", []),
            "generated_checklist": generated_checklist,
        }

    return generator_node


def checklist_converter_wrapper(agent):
    """Wrapper to extract structured metadata from converter agent output."""

    def converter_node(state):
        logger.debug("Checklist converter started")

        result = agent.invoke(state)

        checklist_data = None

        if isinstance(result, dict) and result.get("structured_response"):
            structured_resp = result["structured_response"]
            if hasattr(structured_resp, "model_dump"):
                checklist_data = structured_resp.model_dump()
            elif isinstance(structured_resp, dict):
                checklist_data = structured_resp

        if not checklist_data and result.get("messages"):
            last_message = result["messages"][-1]
            content = getattr(last_message, "content", None)
            if hasattr(content, "model_dump"):
                checklist_data = content.model_dump()
            elif isinstance(content, dict):
                checklist_data = content
            elif isinstance(content, str):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        checklist_data = parsed
                except json.JSONDecodeError:
                    logger.warning("Failed to parse converter content as JSON")

        if checklist_data:
            logger.info("Checklist converter successful")
        else:
            logger.warning("Checklist converter returned no data")

        return {
            "messages": result.get("messages", []),
            "checklist_data": checklist_data,
        }

    return converter_node


# Retry mechanism removed for efficiency - single websearch pass is sufficient


class AgentState:
    """Container for agent instances (mimics old app.state interface)"""
    def __init__(self, llm=None):
        self.llm = llm or get_llm()
        self.qa_chain = get_qa_chain()
        self.chatbot = create_chatbot_agent(self)
        self.websearch_agent = create_websearch_agent(self)
        self.checklist_generator = create_checklist_generator_agent(self)
        self.checklist_converter = create_checklist_converter_agent(self)


def get_router_graph_chat():
    """Chat graph instance (uses GPT-4o-mini for fast responses, cache removed to pick up LLM changes)"""
    agent_state = AgentState(llm=get_llm_chat())
    graph = StateGraph(RouterState)
    graph.add_node("chatbot", agent_state.chatbot)
    graph.add_edge(START, "chatbot")
    graph.add_edge("chatbot", END)
    return graph.compile(checkpointer=checkpointer)


def get_router_graph_generate():
    """Generation graph instance (uses GPT-5-mini for high-quality checklists, cache removed to pick up LLM changes)"""
    agent_state = AgentState(llm=get_llm_checklist())
    graph = StateGraph(RouterState)

    # Simplified linear flow: websearch → checklist generation (no retry for efficiency)
    graph.add_node("websearch_agent", websearch_wrapper(agent_state.websearch_agent))
    graph.add_node("checklist_generator", checklist_generation_wrapper(agent_state.checklist_generator))

    # Linear flow: START → websearch_agent → checklist_generator → END
    graph.add_edge(START, "websearch_agent")
    graph.add_edge("websearch_agent", "checklist_generator")
    graph.add_edge("checklist_generator", END)

    return graph.compile(checkpointer=checkpointer)


def get_router_graph_convert():
    """Conversion graph instance (uses GPT-5-mini for metadata extraction, cache removed to pick up LLM changes)"""
    agent_state = AgentState(llm=get_llm_checklist())
    graph = StateGraph(RouterState)
    graph.add_node("checklist_converter", checklist_converter_wrapper(agent_state.checklist_converter))
    graph.add_edge(START, "checklist_converter")
    graph.add_edge("checklist_converter", END)
    return graph.compile(checkpointer=checkpointer)
