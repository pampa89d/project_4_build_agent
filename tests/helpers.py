"""Вспомогательные функции для интеграционных тестов.

Содержит утилиты для работы с тестовой БД и выполнения SQL.
"""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def get_default_database_url() -> str:
    """Находит тестовую SQLite-базу в папке data/db по шаблону construction*.db.

    Returns:
        str: URL подключения SQLAlchemy (async) к найденной SQLite-базе.

    Raises:
        FileNotFoundError: Если база данных не найдена.
    """
    db_files = sorted((Path("data") / "db").glob("construction*.db"))
    if not db_files:
        raise FileNotFoundError(
            "В папке data/db не найден файл базы данных по шаблону 'construction*.db'"
        )
    return f"sqlite+aiosqlite:///{db_files[0].resolve()}"


async def execute_sql(engine: AsyncEngine, sql: str) -> list[tuple]:
    """Выполняет SQL-запрос и возвращает список кортежей с результатами.

    Args:
        engine: SQLAlchemy AsyncEngine.
        sql: SQL-запрос для выполнения.

    Returns:
        list[tuple]: Строки результата запроса.
    """
    async with engine.connect() as conn:
        result = await conn.execute(text(sql))
        return [tuple(row) for row in result.fetchall()]


def create_test_engine() -> AsyncEngine:
    """Создаёт SQLAlchemy AsyncEngine для тестовой базы данных.

    Returns:
        AsyncEngine: Подключение к тестовой SQLite-базе.
    """
    return create_async_engine(get_default_database_url())
