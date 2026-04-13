"""
Интеграционные тесты: сравнение результатов SQL-запросов с golden dataset.

Запуск:
    pytest tests/test_integration_golden.py --run-integration

Требует:
    - Файл .env с OPEN_ROUTE_API_KEY
    - База данных data/db/construction*.db

Критерии сравнения:
    1. Количество строк в результате actual и golden совпадает.
    2. Первая строка результата actual совпадает с первой строкой golden.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

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


def _execute_sql(engine, sql: str) -> list[tuple]:
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


@pytest.mark.integration
@pytest.mark.parametrize(
    "item",
    json.loads(GOLDEN_PATH.read_text(encoding="utf-8")),
    ids=[item["id"] for item in json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))],
)
def test_sql_result_matches_golden(item, engine, request):
    """Проверяет совпадение результатов SQL пайплайна с эталонным SQL.

    Критерии:
        1. Количество строк в результатах совпадает.
        2. Первая строка в результатах совпадает.

    Args:
        item: Элемент golden dataset с вопросом и эталонным SQL.
        engine: Fixture с подключением к тестовой SQLite-базе.

    Returns:
        None: Сравнивает результаты запросов через assert.
    """
    messages = build_messages(item["question"], engine)
    actual_sql = build_sql_query(messages, REVIEW_PROMPT)

    assert actual_sql not in {
        "Невозможно ответить",
        "Запрещенный SQL-запрос, невозможно ответить",
    }, f"{item['id']}: pipeline вернул отказ вместо SQL: {actual_sql}"

    actual_rows = _execute_sql(engine, actual_sql)
    golden_rows = _execute_sql(engine, item["golden_sql"])

    # Критерий 1: совпадение количества строк
    assert len(actual_rows) == len(golden_rows), (
        f"{item['id']}: количество строк не совпадает\n"
        f"Ожидается: {len(golden_rows)}, получено: {len(actual_rows)}\n"
        f"Golden SQL:\n{item['golden_sql']}\n\n"
        f"Actual SQL:\n{actual_sql}"
    )

    # Критерий 2: совпадение первой строки
    assert actual_rows[0] == golden_rows[0], (
        f"{item['id']}: первая строка результата не совпадает\n"
        f"Ожидается: {golden_rows[0]}\n"
        f"Получено:  {actual_rows[0]}\n"
        f"Golden SQL:\n{item['golden_sql']}\n\n"
        f"Actual SQL:\n{actual_sql}"
    )

    # Запись деталей сравнения в лог
    rows_match = "да" if len(actual_rows) == len(golden_rows) else "нет"
    first_match = "да" if actual_rows[0] == golden_rows[0] else "нет"
    request.node._log_details = [
        f"  Строк: {len(actual_rows)} (совпадает: {rows_match})",
        f"  Первая строка golden: {golden_rows[0]}",
        f"  Первая строка actual: {actual_rows[0]}",
        f"  Совпадение первой строки: {first_match}",
        f"  Actual SQL: {actual_sql}",
    ]
