from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains import RetrievalQA
from .settings import get_settings


def get_vectorstore() -> Chroma:
    """ChromaDB instance (cache removed to allow dynamic config changes)"""
    settings = get_settings()
    return Chroma(
        persist_directory=settings.chroma_persist_directory,
        embedding_function=OpenAIEmbeddings()
    )


def get_llm() -> ChatOpenAI:
    """OpenAI LLM instance (deprecated: use get_llm_chat or get_llm_checklist)"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating ChatOpenAI with model: {settings.llm_model}")
    return ChatOpenAI(model=settings.llm_model, streaming=True)


def get_llm_chat() -> ChatOpenAI:
    """Fast LLM for conversation (cache removed to allow dynamic model changes)"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating ChatOpenAI (chat) with model: {settings.llm_model_chat}")
    return ChatOpenAI(model=settings.llm_model_chat, streaming=True)


def get_llm_checklist() -> ChatOpenAI:
    """High-quality LLM for checklist generation (cache removed to allow dynamic model changes)"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating ChatOpenAI (checklist) with model: {settings.llm_model_checklist}")
    return ChatOpenAI(model=settings.llm_model_checklist, streaming=True)


def get_llm_judge() -> ChatOpenAI:
    """Specialized LLM for lightweight routing/decision making"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating ChatOpenAI (judge) with model: {settings.llm_model_judge}")
    return ChatOpenAI(model=settings.llm_model_judge, streaming=False)


def get_llm_summary() -> ChatOpenAI:
    """Dedicated LLM for summarizing search and pricing results"""
    settings = get_settings()
    print(f"[DEBUG-LLM] Creating ChatOpenAI (summary) with model: {settings.llm_model_summary}")
    return ChatOpenAI(model=settings.llm_model_summary, streaming=False)


def get_qa_chain() -> RetrievalQA:
    """QA chain with RAG retriever"""
    vectorstore = get_vectorstore()
    llm = get_llm()
    return RetrievalQA.from_chain_type(
        llm=llm,
        retriever=vectorstore.as_retriever(),
        return_source_documents=True,
    )
