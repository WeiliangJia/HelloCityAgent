import json
from typing import Any, Dict

from langchain_core.messages import AIMessage

from ..schemas.agent_schema import SearchSummary
from ..utils.prompt_loader import load_prompt

SUMMARY_PROMPT = load_prompt("summary")


class SummaryAgent:
    """Agent that transforms raw search output into a user-facing summary."""

    def __init__(self, llm):
        self.llm = llm.with_structured_output(SearchSummary)

    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        decision = state.get("agent_decision", {}) or {}
        search_results = state.get("search_results")

        prompt = SUMMARY_PROMPT.format(
            decision=decision.get("action", "chat"),
            search_query=decision.get("search_query") or "N/A",
            search_results=json.dumps(search_results, ensure_ascii=False, indent=2) if search_results else "null",
        )

        summary = self.llm.invoke(prompt)
        summary_dict = summary.model_dump() if hasattr(summary, "model_dump") else dict(summary)

        reply_text = summary_dict.get("reply", "").strip()
        if not reply_text:
            reply_text = "I could not find reliable pricing right now. Let me know if you can share more details so I can refine the search."

        new_messages = list(state.get("messages", []))
        new_messages.append(AIMessage(content=reply_text))

        return {
            "messages": new_messages,
            "price_summary": summary_dict,
            "conversation_summary": summary_dict.get("reply"),
        }


def create_summary_agent(state) -> SummaryAgent:
    """Factory to build the summary agent bound to the state's summary LLM."""
    return SummaryAgent(state.llm_summary)
