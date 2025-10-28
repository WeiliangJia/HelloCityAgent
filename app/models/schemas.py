from pydantic import BaseModel
from typing import Annotated, TypedDict, Optional
from langgraph.graph.message import add_messages

class AskRequest(BaseModel):
    # 必需：完整对话历史
    messages: list[dict]

class ChecklistMetadata(BaseModel):
    summary: str
    destination: str
    duration: str
    stay_type: str  # "short-term", "medium-term", "long-term"
    phase_names: list[str]  # List of phases to extract

class GenerateTitleRequest(BaseModel):
    message: str

class GenerateTitleResponse(BaseModel):
    title: str

class TaskSubmitRequest(BaseModel):
    conversationId: str
    messages: list[dict]

class TaskSubmitResponse(BaseModel):
    taskId: str
    status: str  # "pending"

class TaskStatusResponse(BaseModel):
    taskId: str
    status: str  # "pending" | "generating" | "completed" | "failed"
    result: Optional[dict] = None
    error: Optional[str] = None

class RouterState(TypedDict):
    messages: Annotated[list, add_messages]
    checklist_data: Optional[dict]
    generated_checklist: Optional[dict]
    websearch_confidence: Optional[float]
    websearch_retry_count: Optional[int]
