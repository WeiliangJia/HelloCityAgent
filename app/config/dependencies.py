from typing import Dict, Any

from langchain_chroma import Chroma
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import (
    OpenAIEmbeddings,
    ChatOpenAI,
    AzureOpenAIEmbeddings,
    AzureChatOpenAI,
)
from .settings import get_settings


def _build_embeddings(settings):
    """Return embedding model based on OpenAI or Azure configuration."""
    if settings.use_azure_openai:
        if not settings.azure_openai_embeddings_deployment:
            raise ValueError(
                "AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT is required when using Azure OpenAI."
            )
        return AzureOpenAIEmbeddings(
            azure_deployment=settings.azure_openai_embeddings_deployment,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.resolved_api_key,
        )

    return OpenAIEmbeddings(
        model=settings.embeddings_model,
        api_key=settings.resolved_api_key,
    )


def _build_chat_model(settings, model_name: str, streaming: bool) -> BaseChatModel:
    """Return chat model wired for either OpenAI or Azure."""
    if settings.use_azure_openai:
        if not settings.azure_openai_chat_deployment:
            raise ValueError(
                "AZURE_OPENAI_CHAT_DEPLOYMENT is required when using Azure OpenAI."
            )
        return AzureChatOpenAI(
            azure_deployment=settings.azure_openai_chat_deployment,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.resolved_api_key,
            streaming=streaming,
        )

    return ChatOpenAI(
        model=model_name,
        api_key=settings.resolved_api_key,
        streaming=streaming,
    )


def get_vectorstore() -> Chroma:
    """ChromaDB instance (cache removed to allow dynamic config changes)"""
    settings = get_settings()
    embeddings = _build_embeddings(settings)
    return Chroma(
        persist_directory=settings.chroma_persist_directory,
        embedding_function=embeddings
    )


def get_llm() -> BaseChatModel:
    """OpenAI LLM instance (deprecated: use get_llm_chat or get_llm_checklist)"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating LLM with model: {settings.llm_model}")
    return _build_chat_model(settings, settings.llm_model, streaming=True)


def get_llm_chat() -> BaseChatModel:
    """Fast LLM for conversation (cache removed to allow dynamic model changes)"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating LLM (chat) with model: {settings.llm_model_chat}")
    return _build_chat_model(settings, settings.llm_model_chat, streaming=True)


def get_llm_checklist() -> BaseChatModel:
    """High-quality LLM for checklist generation (cache removed to allow dynamic model changes)"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating LLM (checklist) with model: {settings.llm_model_checklist}")
    return _build_chat_model(settings, settings.llm_model_checklist, streaming=True)


def get_llm_judge() -> BaseChatModel:
    """Specialized LLM for lightweight routing/decision making"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating LLM (judge) with model: {settings.llm_model_judge}")
    return _build_chat_model(settings, settings.llm_model_judge, streaming=False)


def get_llm_summary() -> BaseChatModel:
    """Dedicated LLM for summarizing search and pricing results"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating LLM (summary) with model: {settings.llm_model_summary}")
    return _build_chat_model(settings, settings.llm_model_summary, streaming=False)


class SimpleRetrievalQA:
    """Minimal RetrievalQA replacement compatible with langchain-core only installs."""

    def __init__(self, vectorstore: Chroma, llm: BaseChatModel, max_docs: int = 4):
        self.retriever = vectorstore.as_retriever()
        self.llm = llm
        self.max_docs = max_docs

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        query = ""
        if isinstance(inputs, dict):
            query = inputs.get("query") or inputs.get("question") or ""
        elif isinstance(inputs, str):
            query = inputs

        if not query:
            raise ValueError("SimpleRetrievalQA received empty query.")

        documents = self.retriever.get_relevant_documents(query) or []
        top_documents = documents[: self.max_docs]
        if top_documents:
            context_blocks = [
                f"[{idx + 1}] {doc.page_content}" for idx, doc in enumerate(top_documents)
            ]
            context = "\n\n".join(context_blocks)
        else:
            context = "No documents were retrieved from the knowledge base."

        prompt = (
            "You are a travel planning assistant. Use the provided context to answer the user.\n"
            f"Context:\n{context}\n\n"
            f"Question: {query}\n"
            "Answer concisely in the same language as the question."
        )

        response = self.llm.invoke([HumanMessage(content=prompt)])
        answer = getattr(response, "content", str(response))

        return {"result": answer, "source_documents": top_documents}


def get_qa_chain() -> SimpleRetrievalQA:
    """QA chain with RAG retriever"""
    vectorstore = get_vectorstore()
    llm = get_llm()
    return SimpleRetrievalQA(vectorstore, llm)
