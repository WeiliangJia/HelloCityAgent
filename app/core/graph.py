from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage

from ..models.schemas import RouterState
from .hooks import checkpointer
from ..agents import (
    create_chatbot_agent,
    create_websearch_agent,
    create_checklist_generator_agent,
    create_checklist_converter_agent,
    create_rag_agent,
    create_judge_agent,
    create_summary_agent,
)
from ..config.dependencies import (
    get_llm,
    get_llm_chat,
    get_llm_checklist,
    get_qa_chain,
    get_llm_judge,
    get_llm_summary,
)
from ..config.settings import get_settings
from ..utils.logger import setup_logging
from ..utils.tools import make_search_tool
import os
import re
import json

# Initialize logger
logger = setup_logging(log_level=os.getenv("LOG_LEVEL", "INFO"))


def judge_wrapper(agent):
    """Wrapper for the judge agent with robust fallback behaviour."""

    def judge_node(state):
        logger.debug("Judge agent evaluating next action")
        try:
            result = agent.invoke(state)
            decision = (result or {}).get("agent_decision") or {}

            logger.info(
                "Judge decision completed",
                extra={
                    "action": decision.get("action"),
                    "confidence": decision.get("confidence"),
                },
            )

            return {
                "messages": result.get("messages", state.get("messages", [])),
                "agent_decision": decision,
                "search_results": None,
                "price_summary": None,
            }
        except Exception as exc:
            logger.error("Judge agent failed, defaulting to chatbot", exc_info=True)
            fallback_decision = {
                "action": "chat",
                "reason": f"Judge error: {type(exc).__name__}",
                "confidence": 0.0,
                "search_query": None,
                "followups": [],
            }
            return {
                "messages": state.get("messages", []),
                "agent_decision": fallback_decision,
                "search_results": None,
                "price_summary": None,
            }

    return judge_node


def price_search_wrapper(agent_state):
    """Wrapper that runs a single Tavily search for price discovery."""

    def price_search_node(state):
        decision = (state.get("agent_decision") or {})
        query = (decision or {}).get("search_query")

        if not agent_state.settings.enable_web_search:
            logger.info("Web search disabled via settings; skipping search node")
            return {
                "messages": state.get("messages", []),
                "agent_decision": decision,
                "search_results": None,
            }

        if not agent_state.price_search_tool:
            logger.warning("Price search tool unavailable, skipping search execution")
            return {
                "messages": state.get("messages", []),
                "agent_decision": decision,
                "search_results": None,
            }

        if not query:
            logger.warning("Judge did not provide search query; falling back to chatbot path")
            return {
                "messages": state.get("messages", []),
                "agent_decision": decision,
                "search_results": None,
            }

        try:
            logger.info("Executing price search", extra={"query": query})
            search_results = agent_state.price_search_tool.func(query)
            return {
                "messages": state.get("messages", []),
                "agent_decision": decision,
                "search_results": search_results,
            }
        except Exception:
            logger.error("Price search failed", exc_info=True)
            return {
                "messages": state.get("messages", []),
                "agent_decision": decision,
                "search_results": {
                    "error": "Web search failed",
                    "query": query,
                },
            }

    return price_search_node


def summary_wrapper(agent):
    """Wrapper to convert search results into a conversational response."""

    def summary_node(state):
        logger.debug("Summary agent started")
        try:
            result = agent.invoke(state)
            logger.info("Summary agent completed")
            return result
        except Exception:
            logger.error("Summary agent failed", exc_info=True)
            fallback_text = "I was unable to summarize the latest pricing results. Please try refining the dates or destination."
            messages = list(state.get("messages", []))
            messages.append(AIMessage(content=fallback_text))
            return {
                "messages": messages,
                "agent_decision": state.get("agent_decision"),
                "search_results": state.get("search_results"),
                "price_summary": {
                    "reply": fallback_text,
                    "key_points": [],
                    "price_quotes": [],
                    "price_range": None,
                    "recommendation": None,
                    "caution": "Summary agent failed to parse search results.",
                },
                "conversation_summary": fallback_text,
            }

    return summary_node


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
        self.settings = get_settings()
        self.llm = llm or get_llm()
        self.llm_judge = get_llm_judge()
        self.llm_summary = get_llm_summary()
        self.qa_chain = get_qa_chain()

        self.chatbot = create_chatbot_agent(self)
        self.rag_agent = create_rag_agent(self)
        self.judge_agent = create_judge_agent(self)
        self.summary_agent = create_summary_agent(self)
        self.websearch_agent = create_websearch_agent(self)
        self.checklist_generator = create_checklist_generator_agent(self)
        self.checklist_converter = create_checklist_converter_agent(self)

        self.price_search_tool = None
        if self.settings.enable_web_search:
            try:
                self.price_search_tool = make_search_tool()
            except Exception as exc:
                logger.warning("Failed to initialize Tavily search tool", exc_info=True)


def get_router_graph_chat():
    """Chat graph instance (uses GPT-4o-mini for fast responses, cache removed to pick up LLM changes)"""
    agent_state = AgentState(llm=get_llm_chat())
    graph = StateGraph(RouterState)

    graph.add_node("judge", judge_wrapper(agent_state.judge_agent))
    graph.add_node("chatbot", agent_state.chatbot)
    graph.add_node("rag_agent", agent_state.rag_agent)
    graph.add_node("price_search", price_search_wrapper(agent_state))
    graph.add_node("summary_agent", summary_wrapper(agent_state.summary_agent))

    graph.add_edge(START, "judge")

    def _route_after_judge(state):
        decision = (state.get("agent_decision") or {}).get("action", "chat")
        mapping = {
            "chat": "chatbot",
            "rag": "rag_agent",
            "search_flight": "price_search",
            "search_hotel": "price_search",
            "search_general": "price_search",
        }
        next_node = mapping.get(decision, "chatbot")

        if next_node == "rag_agent" and agent_state.rag_agent is None:
            next_node = "chatbot"
        if next_node == "price_search" and agent_state.price_search_tool is None:
            next_node = "chatbot"

        return next_node

    graph.add_conditional_edges(
        "judge",
        _route_after_judge,
        {
            "chatbot": "chatbot",
            "rag_agent": "rag_agent",
            "price_search": "price_search",
        },
    )

    graph.add_edge("chatbot", END)
    graph.add_edge("rag_agent", END)
    graph.add_edge("price_search", "summary_agent")
    graph.add_edge("summary_agent", END)

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
