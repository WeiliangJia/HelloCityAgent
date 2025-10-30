from typing import Any, Dict, List

from ..schemas.agent_schema import AgentDecision
from ..utils.prompt_loader import load_prompt

JUDGE_PROMPT = load_prompt("judge")


def _render_conversation(messages: List[Any]) -> str:
    rendered: List[str] = []
    for message in messages or []:
        role = getattr(message, "type", None) or getattr(message, "role", "user")
        content = getattr(message, "content", None)
        if isinstance(content, list):
            content = " ".join(str(fragment) for fragment in content)
        if isinstance(content, dict):
            content = str(content)
        if content is None:
            content = ""
        rendered.append(f"{role.upper()}: {content}")
    return "\n".join(rendered) if rendered else "USER: (no prior messages)"


class JudgeAgent:
    """Lightweight routing agent that chooses the next action."""

    def __init__(self, llm):
        self.llm = llm.with_structured_output(AgentDecision)

    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        conversation_text = _render_conversation(state.get("messages", []))
        prompt = JUDGE_PROMPT.format(conversation=conversation_text)
        decision = self.llm.invoke(prompt)
        decision_dict = decision.model_dump() if hasattr(decision, "model_dump") else dict(decision)

        return {
            "messages": state.get("messages", []),
            "agent_decision": decision_dict,
        }


def create_judge_agent(state) -> JudgeAgent:
    """Factory to build the judge agent bound to the state's judge LLM."""
    return JudgeAgent(state.llm_judge)
