from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.sql_layer.pipeline import (
    CANNOT_ANSWER,
    PROMPT_INJECTION,
    generate_answer,
    is_cannot_answer,
    normalize_llm_sql_response,
    validate_safe_sql,
)

# ---------------------------------------------------------------------------
# normalize_llm_sql_response
# ---------------------------------------------------------------------------


def test_normalize_strips_sql_markdown():
    """Проверяет удаление SQL markdown-ограждений из ответа модели.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Сверяет нормализованный SQL через assert.
    """
    raw = "```sql\nSELECT 1\n```"
    assert normalize_llm_sql_response(raw) == "SELECT 1"


def test_normalize_strips_plain_markdown():
    """Проверяет удаление обычных markdown-ограждений без указания языка.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Сверяет нормализованный SQL через assert.
    """
    raw = "```\nSELECT 1\n```"
    assert normalize_llm_sql_response(raw) == "SELECT 1"


def test_normalize_returns_cannot_answer_for_empty():
    """Проверяет возврат служебного отказа для пустого ответа модели.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет результат через assert.
    """
    assert normalize_llm_sql_response("") == CANNOT_ANSWER
    assert normalize_llm_sql_response(None) == CANNOT_ANSWER


def test_normalize_returns_cannot_answer_verbatim():
    """Проверяет сохранение стандартного текста отказа без изменений.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет результат через assert.
    """
    assert normalize_llm_sql_response("Невозможно ответить") == CANNOT_ANSWER


def test_normalize_extracts_select_after_preamble():
    """Проверяет извлечение SQL после поясняющего текста модели.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет результат через assert.
    """
    raw = "Вот SQL-запрос:\nSELECT id FROM works"
    assert normalize_llm_sql_response(raw) == "SELECT id FROM works"


def test_normalize_extracts_with_clause():
    """Проверяет извлечение SQL-запроса, начинающегося с WITH.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет результат через assert.
    """
    raw = "Конечно!\nWITH cte AS (SELECT 1) SELECT * FROM cte"
    result = normalize_llm_sql_response(raw)
    assert result.startswith("WITH cte")


# ---------------------------------------------------------------------------
# is_cannot_answer
# ---------------------------------------------------------------------------


def test_is_cannot_answer_exact():
    """Проверяет точное распознавание текста отказа.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет булев результат через assert.
    """
    assert is_cannot_answer("Невозможно ответить") is True


def test_is_cannot_answer_trailing_punct():
    """Проверяет распознавание отказа с завершающей пунктуацией.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет булев результат через assert.
    """
    assert is_cannot_answer("Невозможно ответить.") is True
    assert is_cannot_answer("Невозможно ответить!") is True


def test_is_cannot_answer_false_for_sql():
    """Проверяет, что обычный SQL не считается отказом.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет булев результат через assert.
    """
    assert is_cannot_answer("SELECT 1") is False


def test_is_cannot_answer_none():
    """Проверяет поведение функции на значении None.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет булев результат через assert.
    """
    assert is_cannot_answer(None) is False


# ---------------------------------------------------------------------------
# validate_safe_sql
# ---------------------------------------------------------------------------


def test_validate_allows_select():
    """Проверяет, что обычный SELECT проходит проверку безопасности.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет результат через assert.
    """
    sql = "SELECT id FROM works"
    assert validate_safe_sql(sql) == sql


def test_validate_allows_with():
    """Проверяет, что запрос с CTE и SELECT проходит проверку безопасности.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет результат через assert.
    """
    sql = "WITH cte AS (SELECT 1 AS n) SELECT n FROM cte"
    assert validate_safe_sql(sql) == sql


def test_validate_blocks_insert():
    """Проверяет блокировку INSERT как изменяющего SQL-запроса.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет возбуждение исключения через pytest.raises.
    """
    with pytest.raises(ValueError):
        validate_safe_sql("INSERT INTO works (id) VALUES (1)")


def test_validate_blocks_update():
    """Проверяет блокировку UPDATE как изменяющего SQL-запроса.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет возбуждение исключения через pytest.raises.
    """
    with pytest.raises(ValueError):
        validate_safe_sql("UPDATE works SET work_type = 'X' WHERE id = 1")


def test_validate_blocks_delete():
    """Проверяет блокировку DELETE как изменяющего SQL-запроса.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет возбуждение исключения через pytest.raises.
    """
    with pytest.raises(ValueError):
        validate_safe_sql("DELETE FROM works WHERE id = 1")


def test_validate_blocks_drop():
    """Проверяет блокировку DROP как опасной SQL-конструкции.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет возбуждение исключения через pytest.raises.
    """
    with pytest.raises(ValueError):
        validate_safe_sql("DROP TABLE works")


def test_validate_blocks_pragma():
    """Проверяет блокировку PRAGMA как запрещённого SQL-ключевого слова.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет возбуждение исключения через pytest.raises.
    """
    with pytest.raises(ValueError):
        validate_safe_sql("PRAGMA table_info(works)")


def test_validate_blocks_sqlite_master():
    """Проверяет запрет обращения к служебной таблице sqlite_master.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет возбуждение исключения через pytest.raises.
    """
    with pytest.raises(ValueError, match="sqlite_master"):
        validate_safe_sql("SELECT * FROM sqlite_master")


def test_validate_blocks_empty():
    """Проверяет отклонение пустого SQL-запроса.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет возбуждение исключения через pytest.raises.
    """
    with pytest.raises(ValueError, match="Пустой"):
        validate_safe_sql("")


def test_validate_blocks_multiple_statements():
    """Проверяет запрет нескольких SQL-операторов в одной строке.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет возбуждение исключения через pytest.raises.
    """
    with pytest.raises(ValueError, match="один"):
        validate_safe_sql("SELECT 1; SELECT 2")


# ---------------------------------------------------------------------------
# generate_answer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_answer_passthrough_string():
    """Проверяет, что строка ошибки или отказа возвращается без изменений.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Сравнивает результаты через assert.
    """
    assert await generate_answer("q", CANNOT_ANSWER) == CANNOT_ANSWER
    assert await generate_answer("q", "Ошибка: foo") == "Ошибка: foo"


@pytest.mark.asyncio
async def test_generate_answer_calls_llm_with_rows():
    """Проверяет вызов LLM при генерации ответа из строк SQL-результата.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет ответ и содержимое промпта через assert.
    """
    rows = [(1, "test")]
    llm_mock = AsyncMock(return_value="Ответ")
    with patch("src.sql_layer.pipeline.query_llm", new=llm_mock):
        result = await generate_answer("Сколько объектов?", rows)
    assert result == "Ответ"
    assert llm_mock.call_count == 1
    prompt_content = llm_mock.call_args[0][0][0]["content"]
    assert "Сколько объектов?" in prompt_content
    assert "1 строк" in prompt_content


@pytest.mark.asyncio
async def test_generate_answer_caps_at_50_rows():
    """Проверяет ограничение числа строк, попадающих в промпт генерации ответа.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет содержимое промпта через assert.
    """
    rows = [(i,) for i in range(100)]
    llm_mock = AsyncMock(return_value="ok")
    with patch("src.sql_layer.pipeline.query_llm", new=llm_mock):
        await generate_answer("q", rows)
    prompt_content = llm_mock.call_args[0][0][0]["content"]
    # В промпте должно быть 100 строк как row_count, но только 50 строк данных
    assert "100 строк" in prompt_content
    assert str((50,)) not in prompt_content  # строка 51 не попала
