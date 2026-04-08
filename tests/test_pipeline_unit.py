from unittest.mock import MagicMock, call, patch

import pytest

from src.sql_layer.pipeline import (
    CANNOT_ANSWER,
    PROMPT_INJECTION,
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
    raw = "```sql\nSELECT 1\n```"
    assert normalize_llm_sql_response(raw) == "SELECT 1"


def test_normalize_strips_plain_markdown():
    raw = "```\nSELECT 1\n```"
    assert normalize_llm_sql_response(raw) == "SELECT 1"


def test_normalize_returns_cannot_answer_for_empty():
    assert normalize_llm_sql_response("") == CANNOT_ANSWER
    assert normalize_llm_sql_response(None) == CANNOT_ANSWER


def test_normalize_returns_cannot_answer_verbatim():
    assert normalize_llm_sql_response("Невозможно ответить") == CANNOT_ANSWER


def test_normalize_extracts_select_after_preamble():
    raw = "Вот SQL-запрос:\nSELECT id FROM works"
    assert normalize_llm_sql_response(raw) == "SELECT id FROM works"


def test_normalize_extracts_with_clause():
    raw = "Конечно!\nWITH cte AS (SELECT 1) SELECT * FROM cte"
    result = normalize_llm_sql_response(raw)
    assert result.startswith("WITH cte")


# ---------------------------------------------------------------------------
# is_cannot_answer
# ---------------------------------------------------------------------------


def test_is_cannot_answer_exact():
    assert is_cannot_answer("Невозможно ответить") is True


def test_is_cannot_answer_trailing_punct():
    assert is_cannot_answer("Невозможно ответить.") is True
    assert is_cannot_answer("Невозможно ответить!") is True


def test_is_cannot_answer_false_for_sql():
    assert is_cannot_answer("SELECT 1") is False


def test_is_cannot_answer_none():
    assert is_cannot_answer(None) is False


# ---------------------------------------------------------------------------
# validate_safe_sql
# ---------------------------------------------------------------------------


def test_validate_allows_select():
    sql = "SELECT id FROM works"
    assert validate_safe_sql(sql) == sql


def test_validate_allows_with():
    sql = "WITH cte AS (SELECT 1 AS n) SELECT n FROM cte"
    assert validate_safe_sql(sql) == sql


def test_validate_blocks_insert():
    with pytest.raises(ValueError):
        validate_safe_sql("INSERT INTO works (id) VALUES (1)")


def test_validate_blocks_update():
    with pytest.raises(ValueError):
        validate_safe_sql("UPDATE works SET work_type = 'X' WHERE id = 1")


def test_validate_blocks_delete():
    with pytest.raises(ValueError):
        validate_safe_sql("DELETE FROM works WHERE id = 1")


def test_validate_blocks_drop():
    with pytest.raises(ValueError):
        validate_safe_sql("DROP TABLE works")


def test_validate_blocks_pragma():
    with pytest.raises(ValueError):
        validate_safe_sql("PRAGMA table_info(works)")


def test_validate_blocks_sqlite_master():
    with pytest.raises(ValueError, match="sqlite_master"):
        validate_safe_sql("SELECT * FROM sqlite_master")


def test_validate_blocks_empty():
    with pytest.raises(ValueError, match="Пустой"):
        validate_safe_sql("")


def test_validate_blocks_multiple_statements():
    with pytest.raises(ValueError, match="один"):
        validate_safe_sql("SELECT 1; SELECT 2")


# ---------------------------------------------------------------------------
# execute_sql_query
# ---------------------------------------------------------------------------


def _make_engine_with_rows(rows):
    """Возвращает mock-engine, чей conn.execute(...).fetchall() вернёт rows."""
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
    engine = _make_engine_with_rows([(1,), (2,)])
    with patch("src.sql_layer.pipeline.query_llm", return_value=VALID_SQL):
        result = execute_sql_query(engine, MESSAGES, REVIEW)
    assert result == [(1,), (2,)]


def test_execute_returns_cannot_answer_on_draft_refusal():
    engine = MagicMock()
    with patch("src.sql_layer.pipeline.query_llm", return_value=CANNOT_ANSWER):
        result = execute_sql_query(engine, MESSAGES, REVIEW)
    assert result == CANNOT_ANSWER


def test_execute_returns_prompt_injection_on_invalid_sql():
    engine = MagicMock()
    malicious = "DROP TABLE works"
    with patch("src.sql_layer.pipeline.query_llm", return_value=malicious):
        result = execute_sql_query(engine, MESSAGES, REVIEW)
    assert result == PROMPT_INJECTION


def test_execute_retries_on_execution_error():
    """При ошибке выполнения pipeline делает третий LLM-вызов (исправление)."""
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
    assert generate_answer("q", CANNOT_ANSWER) == CANNOT_ANSWER
    assert generate_answer("q", "Ошибка: foo") == "Ошибка: foo"


def test_generate_answer_calls_llm_with_rows():
    rows = [(1, "test")]
    with patch("src.sql_layer.pipeline.query_llm", return_value="Ответ") as mock_llm:
        result = generate_answer("Сколько объектов?", rows)
    assert result == "Ответ"
    assert mock_llm.call_count == 1
    prompt_content = mock_llm.call_args[0][0][0]["content"]
    assert "Сколько объектов?" in prompt_content
    assert "1 строк" in prompt_content


def test_generate_answer_caps_at_50_rows():
    rows = [(i,) for i in range(100)]
    with patch("src.sql_layer.pipeline.query_llm", return_value="ok") as mock_llm:
        generate_answer("q", rows)
    prompt_content = mock_llm.call_args[0][0][0]["content"]
    # В промпте должно быть 100 строк как row_count, но только 50 строк данных
    assert "100 строк" in prompt_content
    assert str((50,)) not in prompt_content  # строка 51 не попала
