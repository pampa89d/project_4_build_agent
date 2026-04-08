from fastapi import FastAPI

from src.api.routes import router


def create_app() -> FastAPI:
    """Создаёт и настраивает экземпляр FastAPI-приложения.

    Returns:
        FastAPI: Инициализированное приложение с подключёнными маршрутами API.
    """
    app = FastAPI(
        title="Construction Analytics Agent",
        description="Text-to-SQL pipeline over construction database",
        version="0.1.0",
    )
    app.include_router(router)
    return app


app = create_app()
