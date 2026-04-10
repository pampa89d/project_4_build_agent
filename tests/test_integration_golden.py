"""
Интеграционные тесты: сравнение SQL по golden dataset.

Запуск:
    pytest tests/test_integration_golden.py --run-integration

Требует:
    - Файл .env с OPEN_ROUTE_API_KEY
    - База данных data/db/construction*.db
"""

import json
from pathlib import Path
import re

import pytest
from sqlalchemy import create_engine
import sqlglot

from src.sql_layer import REVIEW_PROMPT, build_sql_query
from src.sql_layer.prompts import build_messages

GOLDEN_PATH = Path("data/golden_dataset.json")


def _get_default_database_url() -> str:
    """Находит тестовую SQLite-базу в папке data/db по шаблону construction*.db.

    Args:
        None: Функция не принимает аргументы.

    Returns:
        str: URL подключения SQLAlchemy к найденной SQLite-базе.
    """
    db_files = sorted((Path("data") / "db").glob("construction*.db"))
    if not db_files:
        raise FileNotFoundError(
            "В папке data/db не найден файл базы данных по шаблону 'construction*.db'"
        )
    return f"sqlite:///{db_files[0].resolve()}"


@pytest.fixture(scope="module")
def engine():
    """Создаёт SQLAlchemy engine для интеграционных тестов.

    Args:
        None: Fixture не принимает аргументы.

    Returns:
        object: Подключение к тестовой SQLite-базе.
    """
    return create_engine(_get_default_database_url())


def _normalize_sql(sql: str) -> str:
    """Приводит SQL к общему каноническому виду для синтаксического сравнения.

    Args:
        sql: Исходный SQL-запрос.

    Returns:
        str: Очищенный и канонизированный SQL в диалекте SQLite.
    """
    cleaned = (sql or "").strip()
    cleaned = re.sub(r"```(?:sql)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned)
    cleaned = re.sub(r"--.*?$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r";\s*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    parsed = sqlglot.parse_one(cleaned, read="sqlite")
    return parsed.sql(dialect="sqlite", pretty=True)


@pytest.mark.integration
@pytest.mark.parametrize(
    "item",
    json.loads(GOLDEN_PATH.read_text(encoding="utf-8")),
    ids=[item["id"] for item in json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))],
)
def test_sql_syntax_matches_golden(item, engine):
    """Проверяет совпадение синтаксиса SQL пайплайна с эталонным SQL.

    Args:
        item: Элемент golden dataset с вопросом и эталонным SQL.
        engine: Fixture с подключением к тестовой SQLite-базе.

    Returns:
        None: Сравнивает канонизированные SQL-запросы через assert.
    """
    messages = build_messages(item["question"], engine)
    actual_sql = build_sql_query(messages, REVIEW_PROMPT)

    assert actual_sql not in {
        "Невозможно ответить",
        "Запрещенный SQL-запрос, невозможно ответить",
    }, f"{item['id']}: pipeline вернул отказ вместо SQL: {actual_sql}"

    actual_normalized = _normalize_sql(actual_sql)
    expected_normalized = _normalize_sql(item["golden_sql"])

    assert actual_normalized == expected_normalized, (
        f"{item['id']}: SQL после нормализации не совпадает\n"
        f"Expected SQL:\n{expected_normalized}\n\n"
        f"Actual SQL:\n{actual_normalized}"
    )
