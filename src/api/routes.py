from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.agent.sql_flow import AgentFlow
from src.api.dependencies import get_engine
from src.api.schemas import ChatRequest, ChatResponse, HealthResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest, engine: AsyncEngine = Depends(get_engine)
):
    """Обрабатывает пользовательский вопрос через AgentFlow.

    Args:
        request (ChatRequest): Тело запроса с вопросом пользователя
            и именем модели.
        engine (AsyncEngine): Подключение к БД, передаваемое
            через dependency injection.

    Returns:
        ChatResponse: Ответ API со статусом обработки и количеством
            найденных строк.
    """
    agent = AgentFlow(engine=engine, model_name=request.model_name)
    result = await agent.ask(request.question)

    return ChatResponse(
        answer=result["answer"],
        sql_rows_count=result.get("sql_rows_count"),
        status=result["status"],
    )


@router.get("/health", response_model=HealthResponse)
async def health(engine: AsyncEngine = Depends(get_engine)):
    """Проверяет доступность API и возможность подключения к БД.

    Args:
        engine (AsyncEngine): Подключение к БД, передаваемое
            через dependency injection.

    Returns:
        HealthResponse: Результат health check со статусом
            и признаком доступности БД.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_reachable = True
    except Exception:
        db_reachable = False
    return HealthResponse(status="ok", db_reachable=db_reachable)
