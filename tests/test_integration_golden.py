"""Интеграционные тесты: сравнение результатов SQL-запросов с golden dataset.

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

from src.sql_layer import REVIEW_PROMPT, build_sql_query
from src.sql_layer.prompts import build_messages
from tests.helpers import create_test_engine, execute_sql

GOLDEN_PATH = Path("data/golden_dataset.json")


@pytest.fixture(scope="module")
def engine():
    """Создаёт SQLAlchemy AsyncEngine для интеграционных тестов.

    Returns:
        AsyncEngine: Подключение к тестовой SQLite-базе.
    """
    return create_test_engine()


# тесты с маркером @pytest.mark.integration пропускаются по умолчанию
# и запускаются только с флагом "--run-integration"
@pytest.mark.integration
@pytest.mark.parametrize(
    "item",
    json.loads(GOLDEN_PATH.read_text(encoding="utf-8")),
    ids=[item["id"] for item in json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))],
)
@pytest.mark.asyncio
async def test_sql_result_matches_golden(item, engine, request):
    """Проверяет совпадение результатов SQL пайплайна с эталонным SQL.

    Критерии:
        1. Количество строк в результатах совпадает.
        2. Первая строка в результатах совпадает.

    Args:
        item: Элемент golden dataset с вопросом и эталонным SQL.
        engine: Fixture с подключением к тестовой SQLite-базе.
        request: pytest request для записи логов.

    Returns:
        None: Сравнивает результаты запросов через assert.
    """
    messages = await build_messages(item["question"], engine)
    actual_sql = await build_sql_query(messages, REVIEW_PROMPT)

    assert actual_sql not in {
        "Невозможно ответить",
        "Запрещенный SQL-запрос, невозможно ответить",
    }, f"{item['id']}: pipeline вернул отказ вместо SQL: {actual_sql}"

    actual_rows = await execute_sql(engine, actual_sql)
    golden_rows = await execute_sql(engine, item["golden_sql"])

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
