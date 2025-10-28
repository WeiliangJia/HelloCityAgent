from langchain.agents import Tool
from langchain_tavily import TavilySearch
import os 

def make_qa_tool(qa_chain):
    return Tool(
        name="VectorstoreQASystem",
        func=lambda q: qa_chain.invoke({"query": q}).get("result", ""),
        description="Answer questions based on documents in Chroma"
    )

def make_search_tool():
    tavily_tool = TavilySearch(api_key=os.environ["TAVILY_API_KEY"])
    return Tool(
        name="SearchSystem",
        func=lambda q: str(tavily_tool.invoke({"query": q})),
        description="Search answers on the web using Tavily"
    )
    