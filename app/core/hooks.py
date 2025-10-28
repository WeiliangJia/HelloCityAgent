from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages.utils import trim_messages, count_tokens_approximately

def pre_model_hook(state):
    trimmed_messages = trim_messages(
        state["messages"],
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=16000,
        start_on="human",
        end_on=("human", "tool"),
    )

    return {"llm_input_messages": trimmed_messages}

checkpointer = InMemorySaver()