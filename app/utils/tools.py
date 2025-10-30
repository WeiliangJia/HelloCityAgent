from langchain.agents import Tool
from langchain_tavily import TavilySearch
import os
from typing import Any, Dict


def _ensure_tavily() -> TavilySearch:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("Missing TAVILY_API_KEY environment variable for Tavily search.")
    return TavilySearch(api_key=api_key)


def make_qa_tool(qa_chain):
    return Tool(
        name="VectorstoreQASystem",
        func=lambda q: qa_chain.invoke({"query": q}).get("result", ""),
        description="Answer questions based on documents in Chroma"
    )


def make_search_tool():
    tavily_tool = _ensure_tavily()

    def _search(query: str) -> Dict[str, Any]:
        response = tavily_tool.invoke({
            "query": query,
            "search_depth": "advanced",
            "include_raw_content": True,
            "max_results": 5,
        })
        return response

    return Tool(
        name="SearchSystem",
        func=_search,
        description="Perform a focused web search (flights, hotels, pricing) and return structured JSON."
    )
