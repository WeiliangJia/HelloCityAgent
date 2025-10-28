import os
from dotenv import load_dotenv

from langchain_community.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

load_dotenv(".env.local")

local_loader = DirectoryLoader("./documentation", glob="**/*.*")
local_docs = local_loader.load()

docs = local_docs #loader.load() + local_docs

splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
splits = splitter.split_documents(docs)

embeddings = OpenAIEmbeddings(
    api_key=os.getenv("OPENAI_API_KEY"),
    model=os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")
)

vectorstore = Chroma.from_documents(
    documents=splits,
    embedding=embeddings,
    persist_directory="../chroma_db" 
)

vectorstore.persist()
print("Vectorstore persisted to ./chroma_db")