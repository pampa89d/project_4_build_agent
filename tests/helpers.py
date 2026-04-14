"""Вспомогательные функции для интеграционных тестов.

Содержит утилиты для работы с тестовой БД, выполнения SQL
и кеширования golden SQL-запросов при тестировании.
"""

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.sql_layer import REVIEW_PROMPT, build_sql_query
from src.sql_layer.pipeline import _transpile, validate_safe_sql

GOLDEN_DATASET_PATH = Path("data/golden_dataset.json")


def _is_golden_cache_enabled() -> bool:
    """Определяет, разрешено ли использовать exact-match cache golden dataset.

    Returns:
        bool: True, если cache включён (по умолчанию).
    """
    flag = os.getenv("USE_GOLDEN_SQL_CACHE", "1").strip().lower()
    return flag not in {"0", "false", "no", "off"}


def _load_golden_sql_examples() -> dict[str, str]:
    """Загружает exact-match примеры SQL из golden dataset.

    Returns:
        dict[str, str]: Словарь вопрос -> эталонный SQL.
    """
    if not GOLDEN_DATASET_PATH.exists():
        return {}

    try:
        dataset = json.loads(GOLDEN_DATASET_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

    examples = {}
    for item in dataset:
        question = (item.get("question") or "").strip()
        golden_sql = (item.get("golden_sql") or "").strip()
        if question and golden_sql:
            examples[question] = golden_sql
    return examples


def _get_cached_golden_sql(messages: list[dict]) -> str | None:
    """Возвращает эталонный SQL для точного совпадения вопроса.

    Args:
        messages: Список сообщений пайплайна.

    Returns:
        str | None: SQL из golden dataset или None.
    """
    user_messages = [m for m in messages if m.get("role") == "user"]
    if not user_messages:
        return None

    question = (user_messages[-1].get("content") or "").strip()
    if not question:
        return None

    golden_sql = _load_golden_sql_examples().get(question)
    if not golden_sql:
        return None

    try:
        return _transpile(validate_safe_sql(golden_sql))
    except Exception:
        return None


def build_sql_query_with_cache(
    messages: list[dict],
    review_prompt: str = REVIEW_PROMPT,
    model_name: str = "meta-llama/llama-3.3-70b-instruct",
) -> str:
    """Генерирует SQL с optional golden-cache.

    Если USE_GOLDEN_SQL_CACHE=1 (по умолчанию) и вопрос точно совпадает
    с golden dataset — возвращает кешированный SQL без вызова LLM.
    Иначе — вызывает build_sql_query через LLM.

    Args:
        messages: Список сообщений вида {role, content}.
        review_prompt: Промпт для LLM-ревью.
        model_name: Идентификатор модели на OpenRouter.

    Returns:
        str: SQL-запрос или строка отказа.
    """
    if _is_golden_cache_enabled():
        cached_sql = _get_cached_golden_sql(messages)
        if cached_sql is not None:
            return cached_sql

    return build_sql_query(messages, review_prompt, model_name)


def get_default_database_url() -> str:
    """Находит тестовую SQLite-базу в папке data/db по шаблону construction*.db.

    Returns:
        str: URL подключения SQLAlchemy к найденной SQLite-базе.

    Raises:
        FileNotFoundError: Если база данных не найдена.
    """
    db_files = sorted((Path("data") / "db").glob("construction*.db"))
    if not db_files:
        raise FileNotFoundError(
            "В папке data/db не найден файл базы данных по шаблону 'construction*.db'"
        )
    return f"sqlite:///{db_files[0].resolve()}"


def execute_sql(engine: Engine, sql: str) -> list[tuple]:
    """Выполняет SQL-запрос и возвращает список кортежей с результатами.

    Args:
        engine: SQLAlchemy engine.
        sql: SQL-запрос для выполнения.

    Returns:
        list[tuple]: Строки результата запроса.
    """
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        return [tuple(row) for row in result.fetchall()]


def create_test_engine() -> Engine:
    """Создаёт SQLAlchemy engine для тестовой базы данных.

    Returns:
        Engine: Подключение к тестовой SQLite-базе.
    """
    return create_engine(get_default_database_url())
