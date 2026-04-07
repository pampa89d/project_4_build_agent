import re

from sqlalchemy import text
from sqlalchemy.engine import Engine
import sqlglot
from sqlglot import exp

from src.llm_client import query_llm

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
CANNOT_ANSWER = "Невозможно ответить"
PROMPT_INJECTION = "Запрещенный SQL-запрос, невозможно ответить"
REFUSAL_RESPONSES = {
    CANNOT_ANSWER,
    PROMPT_INJECTION,
}

DISALLOWED_SQL_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.Command,
    exp.Merge,
    exp.Union,
)

DISALLOWED_SQL_KEYWORDS = (
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "VACUUM",
    "REINDEX",
    "ANALYZE",
    "REPLACE",
    "EXECUTE",
    "CALL",
)

DISALLOWED_TABLE_NAMES = {
    "sqlite_master",
}


def strip_markdown_sql(response: str | None) -> str:
    """Возвращает чистый SQL, даже если модель обернула его в markdown."""
    cleaned = (response or "").strip()
    fenced_match = re.search(
        r"```(?:sql)?\s*\n?(.*?)```", cleaned, re.DOTALL | re.IGNORECASE
    )
    if fenced_match:
        return fenced_match.group(1).strip()
    return cleaned


def is_cannot_answer(response: str | None) -> bool:
    """Проверяет, является ли ответ модели сигналом о невозможности построить запрос."""
    normalized = (response or "").strip().rstrip(" .!?").strip()
    return normalized in REFUSAL_RESPONSES


def normalize_llm_sql_response(response: str | None) -> str:
    """Преобразует ответ LLM в чистый SQL или один из refusal-ответов."""
    cleaned = strip_markdown_sql(response)

    if not cleaned:
        return CANNOT_ANSWER

    if is_cannot_answer(cleaned):
        normalized = cleaned.strip().rstrip(" .!?").strip()
        return normalized

    # Ищем первое вхождение SQL, чтобы отрезать возможные пояснения модели.
    sql_match = re.search(r"(?is)\b(WITH|SELECT)\b.*", cleaned)
    if sql_match:
        return sql_match.group(0).strip()

    for refusal_response in REFUSAL_RESPONSES:
        if refusal_response in cleaned:
            return refusal_response

    return cleaned


def validate_safe_sql(sql: str) -> str:
    """Разрешает только один read-only SQL-запрос для SQLite."""
    raw_sql = (sql or "").strip()
    if not raw_sql:
        raise ValueError("Пустой SQL-запрос")

    parsed = sqlglot.parse(raw_sql, read="sqlite")
    if len(parsed) != 1:
        raise ValueError("Разрешен только один SQL-запрос")

    expression = parsed[0]

    if not isinstance(expression, exp.Query):
        raise ValueError("Разрешены только SELECT/WITH-запросы")

    for node_type in DISALLOWED_SQL_NODES:
        if expression.find(node_type):
            raise ValueError(
                f"Обнаружена запрещенная SQL-конструкция: {node_type.__name__}"
            )

    for table in expression.find_all(exp.Table):
        if table.name and table.name.lower() in DISALLOWED_TABLE_NAMES:
            raise ValueError(
                f"Обнаружено обращение к запрещенной таблице: {table.name}"
            )

    upper_sql = raw_sql.upper()
    for keyword in DISALLOWED_SQL_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper_sql):
            raise ValueError(f"Обнаружено запрещенное SQL-ключевое слово: {keyword}")

    return raw_sql


def _validate_or_cannot_answer(sql: str) -> str:
    """Возвращает SQL без изменений или PROMPT_INJECTION при срабатывании защиты."""
    try:
        return validate_safe_sql(sql)
    except Exception:
        return PROMPT_INJECTION


def _transpile(sql: str) -> str:
    """Преобразует SQL в стандартизированный формат."""
    return sqlglot.transpile(sql, read="sqlite", write="sqlite", pretty=True)[0]


def execute_sql_query(
    engine: Engine,
    messages: list[dict],
    review_prompt: str,
    model_name: str = DEFAULT_MODEL,
) -> list[tuple] | str:
    """Генерирует, проверяет и выполняет SQL-запрос.

    Args:
        engine: SQLAlchemy engine.
        messages: Список сообщений [{role, content}]. Не мутируется.
        review_prompt: Промпт для LLM-проверки сгенерированного SQL.
        model_name: Идентификатор модели на OpenRouter.

    Returns:
        Список строк результата или строка с ошибкой / refusal-ответом.
    """
    working_messages = [m.copy() for m in messages]

    # Stage 1: генерация чернового SQL
    draft_sql = query_llm(working_messages, model_name)
    draft_sql_clean = normalize_llm_sql_response(draft_sql)

    if is_cannot_answer(draft_sql_clean):
        return CANNOT_ANSWER

    draft_sql_clean = _validate_or_cannot_answer(draft_sql_clean)
    if is_cannot_answer(draft_sql_clean):
        return PROMPT_INJECTION

    formatted_draft = _transpile(draft_sql_clean)
    working_messages.append({"role": "assistant", "content": formatted_draft})
    working_messages.append({"role": "user", "content": review_prompt})

    # Stage 2: review — LLM проверяет и исправляет SQL
    reviewed_sql = query_llm(working_messages, model_name)
    reviewed_sql_clean = normalize_llm_sql_response(reviewed_sql)

    if is_cannot_answer(reviewed_sql_clean):
        return CANNOT_ANSWER

    reviewed_sql_clean = _validate_or_cannot_answer(reviewed_sql_clean)
    if is_cannot_answer(reviewed_sql_clean):
        return PROMPT_INJECTION

    allowed_query = _transpile(reviewed_sql_clean)

    # Stage 3: выполнение
    try:
        with engine.connect() as conn:
            result = conn.execute(text(allowed_query))
        return result.fetchall()
    except Exception as err:
        error_fix_prompt = (
            f"Предыдущий SQL-запрос вызвал ошибку выполнения: {err}. "
            "Исправь SQL-запрос так, чтобы он соответствовал SYSTEM_PROMPT. "
            "Проверь валидность фильтрации, works.unit при агрегации объемов, "
            "отсутствие progress.unit и отсутствие даты без явного запроса "
            "пользователя. Если корректный SQL построить нельзя, верни ровно: "
            "Невозможно ответить. Верни ровно один исправленный SQL-запрос без "
            "объяснений, без markdown, без комментариев и без лишнего текста."
        )
        working_messages.append({"role": "assistant", "content": allowed_query})
        working_messages.append({"role": "user", "content": error_fix_prompt})

        fixed_sql = query_llm(working_messages, model_name)
        fixed_sql_clean = normalize_llm_sql_response(fixed_sql)

        if is_cannot_answer(fixed_sql_clean):
            return CANNOT_ANSWER

        fixed_sql_clean = _validate_or_cannot_answer(fixed_sql_clean)
        if is_cannot_answer(fixed_sql_clean):
            return PROMPT_INJECTION

        try:
            fixed_query = _transpile(fixed_sql_clean)
            with engine.connect() as conn:
                result = conn.execute(text(fixed_query))
            return result.fetchall()
        except Exception as fix_err:
            return f"Ошибка после попытки исправления: {fix_err}"
