from unittest.mock import MagicMock, patch

import pytest

from src.sql_layer.pipeline import (
    CANNOT_ANSWER,
    PROMPT_INJECTION,
    build_sql_query,
    execute_sql_query,
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
# execute_sql_query
# ---------------------------------------------------------------------------


def _make_engine_with_rows(rows):
    """Создаёт mock engine, возвращающий заранее заданные строки результата.

    Args:
        rows: Последовательность строк, которую должен вернуть fetchall().

    Returns:
        MagicMock: Настроенный mock engine для тестирования SQL-пайплайна.
    """
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value = mock_result
    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


VALID_SQL = "SELECT id FROM works"
MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]
REVIEW = "Проверь SQL"


def test_execute_returns_rows_on_success():
    """Проверяет успешное выполнение пайплайна при корректном SQL и ответе БД.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Сравнивает фактический результат через assert.
    """
    engine = _make_engine_with_rows([(1,), (2,)])
    with patch("src.sql_layer.pipeline.query_llm", return_value=VALID_SQL):
        result = execute_sql_query(engine, MESSAGES, REVIEW)
    assert result == [(1,), (2,)]


def test_build_sql_query_uses_cached_golden_sql_on_exact_question_match():
    """Проверяет, что exact-match вопрос берёт SQL из golden dataset без вызова LLM.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет результат и отсутствие вызовов LLM через assert.
    """
    messages = [{"role": "user", "content": "Сколько объектов в каждом городе?"}]
    cached = {"Сколько объектов в каждом городе?": "SELECT city FROM objects"}

    with (
        patch("src.sql_layer.pipeline._load_golden_sql_examples", return_value=cached),
        patch("src.sql_layer.pipeline.query_llm") as mock_llm,
    ):
        result = build_sql_query(messages, REVIEW)

    assert result == "SELECT\n  city\nFROM objects"
    mock_llm.assert_not_called()


def test_execute_sql_query_uses_cached_golden_sql_on_exact_question_match():
    """Проверяет, что execute_sql_query использует cached SQL и не вызывает LLM.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет результат выполнения и отсутствие вызовов LLM через assert.
    """
    engine = _make_engine_with_rows([(7,)])
    messages = [{"role": "user", "content": "Сколько объектов в каждом городе?"}]
    cached = {"Сколько объектов в каждом городе?": "SELECT city FROM objects"}

    with (
        patch("src.sql_layer.pipeline._load_golden_sql_examples", return_value=cached),
        patch("src.sql_layer.pipeline.query_llm") as mock_llm,
    ):
        result = execute_sql_query(engine, messages, REVIEW)

    assert result == [(7,)]
    mock_llm.assert_not_called()


def test_build_sql_query_skips_cached_golden_sql_when_env_flag_disabled():
    """Проверяет, что golden cache можно отключить через переменную окружения.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет, что вызывается LLM, а не cached SQL.
    """
    messages = [{"role": "user", "content": "Сколько объектов в каждом городе?"}]
    cached = {"Сколько объектов в каждом городе?": "SELECT city FROM objects"}

    with (
        patch("src.sql_layer.pipeline._load_golden_sql_examples", return_value=cached),
        patch.dict("os.environ", {"USE_GOLDEN_SQL_CACHE": "0"}),
        patch(
            "src.sql_layer.pipeline.query_llm", side_effect=[VALID_SQL, VALID_SQL]
        ) as mock_llm,
    ):
        result = build_sql_query(messages, REVIEW)

    assert result == "SELECT\n  id\nFROM works"
    assert mock_llm.call_count == 2


def test_execute_returns_cannot_answer_on_draft_refusal():
    """Проверяет возврат отказа, если первый ответ модели равен CANNOT_ANSWER.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Сравнивает фактический результат через assert.
    """
    engine = MagicMock()
    with patch("src.sql_layer.pipeline.query_llm", return_value=CANNOT_ANSWER):
        result = execute_sql_query(engine, MESSAGES, REVIEW)
    assert result == CANNOT_ANSWER


def test_execute_returns_prompt_injection_on_invalid_sql():
    """Проверяет возврат защиты от prompt injection при опасном SQL.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Сравнивает фактический результат через assert.
    """
    engine = MagicMock()
    malicious = "DROP TABLE works"
    with patch("src.sql_layer.pipeline.query_llm", return_value=malicious):
        result = execute_sql_query(engine, MESSAGES, REVIEW)
    assert result == PROMPT_INJECTION


def test_execute_retries_on_execution_error():
    """Проверяет повторный вызов LLM после ошибки выполнения SQL в БД.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет количество вызовов и итоговый результат через assert.
    """
    rows = [(42,)]

    error_conn = MagicMock()
    error_conn.__enter__ = MagicMock(return_value=error_conn)
    error_conn.__exit__ = MagicMock(return_value=False)
    error_conn.execute.side_effect = [Exception("DB error"), MagicMock()]

    success_result = MagicMock()
    success_result.fetchall.return_value = rows
    ok_conn = MagicMock()
    ok_conn.__enter__ = MagicMock(return_value=ok_conn)
    ok_conn.__exit__ = MagicMock(return_value=False)
    ok_conn.execute.return_value = success_result

    engine = MagicMock()
    engine.connect.side_effect = [error_conn, ok_conn]

    llm_calls = [VALID_SQL, VALID_SQL, VALID_SQL]
    with patch("src.sql_layer.pipeline.query_llm", side_effect=llm_calls) as mock_llm:
        result = execute_sql_query(engine, MESSAGES, REVIEW)

    assert mock_llm.call_count == 3
    assert result == rows


# ---------------------------------------------------------------------------
# generate_answer
# ---------------------------------------------------------------------------


def test_generate_answer_passthrough_string():
    """Проверяет, что строка ошибки или отказа возвращается без изменений.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Сравнивает результаты через assert.
    """
    assert generate_answer("q", CANNOT_ANSWER) == CANNOT_ANSWER
    assert generate_answer("q", "Ошибка: foo") == "Ошибка: foo"


def test_generate_answer_calls_llm_with_rows():
    """Проверяет вызов LLM при генерации ответа из строк SQL-результата.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет ответ и содержимое промпта через assert.
    """
    rows = [(1, "test")]
    with patch("src.sql_layer.pipeline.query_llm", return_value="Ответ") as mock_llm:
        result = generate_answer("Сколько объектов?", rows)
    assert result == "Ответ"
    assert mock_llm.call_count == 1
    prompt_content = mock_llm.call_args[0][0][0]["content"]
    assert "Сколько объектов?" in prompt_content
    assert "1 строк" in prompt_content


def test_generate_answer_caps_at_50_rows():
    """Проверяет ограничение числа строк, попадающих в промпт генерации ответа.

    Args:
        None: Тест не принимает аргументы.

    Returns:
        None: Проверяет содержимое промпта через assert.
    """
    rows = [(i,) for i in range(100)]
    with patch("src.sql_layer.pipeline.query_llm", return_value="ok") as mock_llm:
        generate_answer("q", rows)
    prompt_content = mock_llm.call_args[0][0][0]["content"]
    # В промпте должно быть 100 строк как row_count, но только 50 строк данных
    assert "100 строк" in prompt_content
    assert str((50,)) not in prompt_content  # строка 51 не попала
