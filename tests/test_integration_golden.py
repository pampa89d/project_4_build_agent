"""
Интеграционные тесты: Execution Accuracy по golden dataset.

Запуск:
    pytest tests/test_integration_golden.py --run-integration

Требует:
    - Файл .env с OPEN_ROUTE_API_KEY
    - База данных data/db/construction*.db
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from src.sql_layer import REVIEW_PROMPT, execute_sql_query
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


def _normalize_rows(rows):
    """Нормализует строки результата для устойчивого сравнения.

    Args:
        rows: Последовательность строк результата SQL-запроса.

    Returns:
        set: Множество кортежей с округлением float до двух знаков.
    """
    return {
        tuple(round(v, 2) if isinstance(v, float) else v for v in row) for row in rows
    }


@pytest.mark.integration
@pytest.mark.parametrize(
    "item",
    json.loads(GOLDEN_PATH.read_text(encoding="utf-8")),
    ids=[item["id"] for item in json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))],
)
def test_execution_accuracy(item, engine):
    """Проверяет совпадение результата пайплайна с эталонным SQL из golden dataset.

    Args:
        item: Элемент golden dataset с вопросом и эталонным SQL.
        engine: Fixture с подключением к тестовой SQLite-базе.

    Returns:
        None: Сравнивает ожидаемые и фактические строки через assert.
    """
    messages = build_messages(item["question"], engine)
    actual = execute_sql_query(engine, messages, REVIEW_PROMPT)

    assert isinstance(actual, list), (
        f"{item['id']}: pipeline вернул ошибку вместо строк: {actual}"
    )

    with engine.connect() as conn:
        expected = conn.execute(text(item["golden_sql"])).fetchall()

    assert _normalize_rows(actual) == _normalize_rows(expected), (
        f"{item['id']}: ожидалось {len(expected)} строк, получено {len(actual)}\n"
        f"Expected sample: {list(expected)[:3]}\n"
        f"Actual sample:   {list(actual)[:3]}"
    )
