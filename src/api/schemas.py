from pydantic import BaseModel, Field

from src.sql_layer.pipeline import DEFAULT_MODEL


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    model_name: str = Field(default=DEFAULT_MODEL)


class ChatResponse(BaseModel):
    answer: str
    sql_rows_count: int | None = None
    status: str  # "ok" | "cannot_answer" | "error"


class HealthResponse(BaseModel):
    status: str
    db_reachable: bool
