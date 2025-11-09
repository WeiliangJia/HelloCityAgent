import os
import argparse
import asyncio
import uuid
from typing import List

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

# Import from app package
from app.core.graph import get_router_graph_chat


def load_env():
    # Load .env.local if present
    here = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(here, ".env.local")
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)


async def run_chat(session_id: str, stream: bool):
    graph = get_router_graph_chat()
    history: List = []

    print(f"Session: {session_id}\nType '/quit' to exit, '/reset' to clear history.\n")
    while True:
        try:
            user = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye")
            break

        if not user:
            continue
        if user.lower() in {"/q", "/quit", "exit"}:
            print("Bye")
            break
        if user.lower() in {"/r", "/reset"}:
            history.clear()
            print("History cleared.")
            continue

        history.append(HumanMessage(content=user))

        if stream:
            print("Assistant: ", end="", flush=True)
            accumulated = ""
            async for event in graph.astream_events(
                {"messages": history},
                config={"configurable": {"thread_id": session_id}},
                version="v2",
            ):
                if event.get("event") == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    text = getattr(chunk, "content", "") or ""
                    if text:
                        print(text, end="", flush=True)
                        accumulated += text
            print()
            history.append(AIMessage(content=accumulated if accumulated else ""))
        else:
            result = await graph.ainvoke(
                {"messages": history},
                config={"configurable": {"thread_id": session_id}},
            )
            # The final AI message should be last in messages
            messages = result.get("messages", [])
            ai_text = ""
            if messages:
                last = messages[-1]
                ai_text = getattr(last, "content", "") or str(last)
            print(f"Assistant: {ai_text}")
            history = messages  # keep full state returned by graph


def main():
    load_env()

    parser = argparse.ArgumentParser(description="Terminal chat using LangGraph pipeline")
    parser.add_argument("--session", default=str(uuid.uuid4()), help="Session/thread id")
    parser.add_argument("--stream", action="store_true", help="Stream tokens to terminal")
    args = parser.parse_args()

    # Helpful hints
    if not os.environ.get("OPENAI_API_KEY"):
        print("[WARN] OPENAI_API_KEY is not set. Set it in .env.local or environment.")

    try:
        asyncio.run(run_chat(args.session, args.stream))
    except KeyboardInterrupt:
        print("\nBye")


if __name__ == "__main__":
    main()

