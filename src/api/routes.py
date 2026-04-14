from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.api.dependencies import get_engine
from src.api.schemas import ChatRequest, ChatResponse, HealthResponse
from src.sql_layer import CANNOT_ANSWER, REVIEW_PROMPT, execute_sql_query
from src.sql_layer.pipeline import generate_answer
from src.sql_layer.prompts import build_messages

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest, engine: AsyncEngine = Depends(get_engine)
):
    """Обрабатывает пользовательский вопрос и возвращает текстовый ответ агента.

    Args:
        request (ChatRequest): Тело запроса с вопросом пользователя и именем модели.
        engine (AsyncEngine): Подключение к БД, передаваемое через dependency injection.

    Returns:
        ChatResponse: Ответ API со статусом обработки и количеством найденных строк.
    """
    messages = await build_messages(request.question, engine)
    sql_result = await execute_sql_query(
        engine, messages, REVIEW_PROMPT, request.model_name
    )
    answer = await generate_answer(request.question, sql_result, request.model_name)

    if isinstance(sql_result, list):
        return ChatResponse(
            answer=answer,
            sql_rows_count=len(sql_result),
            status="ok",
        )
    if sql_result == CANNOT_ANSWER:
        return ChatResponse(answer=answer, status="cannot_answer")
    return ChatResponse(answer=answer, status="error")


@router.get("/health", response_model=HealthResponse)
async def health(engine: AsyncEngine = Depends(get_engine)):
    """Проверяет доступность API и возможность подключения к базе данных.

    Args:
        engine (AsyncEngine): Подключение к БД, передаваемое через dependency injection.

    Returns:
        HealthResponse: Результат health check со статусом и признаком доступности БД.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_reachable = True
    except Exception:
        db_reachable = False
    return HealthResponse(status="ok", db_reachable=db_reachable)
