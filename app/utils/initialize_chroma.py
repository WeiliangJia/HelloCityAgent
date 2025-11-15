import sys
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings, AzureOpenAIEmbeddings

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.config.settings import get_settings  # noqa: E402

settings = get_settings()

local_loader = DirectoryLoader("./documentation", glob="**/*.*")
local_docs = local_loader.load()

docs = local_docs #loader.load() + local_docs

splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
splits = splitter.split_documents(docs)

if settings.use_azure_openai:
    if not settings.azure_openai_embeddings_deployment:
        raise ValueError("Configure AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT before running this script.")
    embeddings = AzureOpenAIEmbeddings(
        azure_deployment=settings.azure_openai_embeddings_deployment,
        api_version=settings.azure_openai_api_version,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.resolved_api_key,
    )
else:
    embeddings = OpenAIEmbeddings(
        api_key=settings.resolved_api_key,
        model=settings.embeddings_model,
    )

vectorstore = Chroma.from_documents(
    documents=splits,
    embedding=embeddings,
    persist_directory=settings.chroma_persist_directory
)

vectorstore.persist()
print(f"Vectorstore persisted to {settings.chroma_persist_directory}")
