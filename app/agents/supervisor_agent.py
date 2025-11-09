from typing import Any, Dict, List


BASE_PROMPT = (
    "You are a strict but helpful supervisor. "
    "Reflect on the assistant's draft vs the user's request. "
    "Identify concrete gaps, propose up to 3 crisp improvements, "
    "and include a short improved reply under 'Revision:' if it helps."
)


class SupervisorAgent:
    def __init__(self, llm):
        # Reuse summary-capable LLM for low latency/cost
        self.llm = llm

    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[Any] = state.get("messages", [])

        # latest AI and user messages
        last_ai = next(
            (m for m in reversed(messages) if getattr(m, "type", getattr(m, "role", "")) in ["ai", "assistant"]),
            None,
        )
        last_user = next(
            (m for m in reversed(messages) if getattr(m, "type", getattr(m, "role", "")) in ["human", "user"]),
            None,
        )

        ai_text = getattr(last_ai, "content", "") if last_ai else ""
        user_text = getattr(last_user, "content", "") if last_user else ""

        header = state.get("supervisor_header") or ""
        prompt = (f"{BASE_PROMPT}\n\n{header}\n" if header else f"{BASE_PROMPT}\n")
        prompt += (
            f"\nUser request:\n{user_text}\n\n"
            f"Assistant draft:\n{ai_text}\n\n"
            "Return in this format:\n"
            "- Gaps: <bullet points>\n"
            "- Improvements: <bullet points>\n"
            "- Revision: <one short improved reply or 'None'>\n"
        )

        feedback = self.llm.invoke(prompt)
        text = getattr(feedback, "content", str(feedback)).strip()

        revision = None
        if "Revision:" in text:
            revision_part = text.split("Revision:", 1)[1].strip()
            if revision_part and revision_part.lower() != "none":
                revision = revision_part

        return {
            "messages": messages,
            "supervisor_feedback": text,
            "supervisor_revision": revision,
        }


def create_supervisor_agent(state) -> SupervisorAgent:
    # Use state's summary LLM if available
    return SupervisorAgent(state.llm_summary)

