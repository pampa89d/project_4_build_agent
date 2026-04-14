import re

from sqlalchemy import text
from sqlalchemy.engine import Engine
import sqlglot
from sqlglot import exp

from src.agent.llm_client import query_llm

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
SQL_TEMPERATURE = 0.0
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
    """Извлекает SQL из ответа модели, удаляя markdown-обёртки.

    Args:
        response (str | None): Исходный текстовый ответ модели.

    Returns:
        str: Очищенный SQL или исходный текст без внешних пробелов.
    """
    cleaned = (response or "").strip()
    fenced_match = re.search(
        r"```(?:sql)?\s*\n?(.*?)```", cleaned, re.DOTALL | re.IGNORECASE
    )
    if fenced_match:
        return fenced_match.group(1).strip()
    return cleaned


def is_cannot_answer(response: str | None) -> bool:
    """Проверяет, означает ли ответ отказ от построения SQL.

    Args:
        response (str | None): Текст ответа модели.

    Returns:
        bool: True, если ответ соответствует одному из вариантов отказа.
    """
    normalized = (response or "").strip().rstrip(" .!?").strip()
    return normalized in REFUSAL_RESPONSES


def normalize_llm_sql_response(response: str | None) -> str:
    """Нормализует ответ LLM до чистого SQL или служебного отказа.

    Args:
        response (str | None): Исходный ответ модели.

    Returns:
        str: SQL-запрос без лишнего текста либо строка отказа.
    """
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
    """Проверяет, что SQL безопасен и содержит только один read-only запрос.

    Args:
        sql (str): SQL-запрос для проверки.

    Returns:
        str: Тот же SQL-запрос, если он прошёл проверку безопасности.
    """
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
    """Проверяет SQL и заменяет небезопасный запрос на служебный отказ.

    Args:
        sql (str): SQL-запрос для проверки.

    Returns:
        str: Исходный SQL или строка PROMPT_INJECTION.
    """
    try:
        return validate_safe_sql(sql)
    except Exception:
        return PROMPT_INJECTION


def _transpile(sql: str) -> str:
    """Нормализует формат SQL-запроса средствами sqlglot.

    Args:
        sql (str): SQL-запрос в диалекте SQLite.

    Returns:
        str: Отформатированный SQL-запрос.
    """
    return sqlglot.transpile(sql, read="sqlite", write="sqlite", pretty=True)[0]


def execute_sql_query(
    engine: Engine,
    messages: list[dict],
    review_prompt: str,
    model_name: str = DEFAULT_MODEL,
) -> list[tuple] | str:
    """Генерирует, проверяет, при необходимости исправляет и выполняет SQL-запрос.

    Args:
        engine (Engine): SQLAlchemy engine для выполнения запросов.
        messages (list[dict]): Список сообщений вида {role, content}. Исходный список не мутируется.
        review_prompt (str): Промпт для второго прохода LLM-проверки SQL.
        model_name (str): Идентификатор модели на OpenRouter.

    Returns:
        list[tuple] | str: Результат SQL-запроса в виде списка строк либо строка ошибки/отказа.
    """
    working_messages = [m.copy() for m in messages]

    # Stage 1: генерация чернового SQL
    draft_sql = query_llm(working_messages, model_name, temperature=SQL_TEMPERATURE)
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
    reviewed_sql = query_llm(working_messages, model_name, temperature=SQL_TEMPERATURE)
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

        fixed_sql = query_llm(working_messages, model_name, temperature=SQL_TEMPERATURE)
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


_ANSWER_PROMPT_TEMPLATE = (
    "Пользователь спросил: {question}\n\n"
    "Результат SQL-запроса ({row_count} строк):\n{rows_text}\n\n"
    "Сформулируй краткий и понятный ответ на русском языке.\n"
    "Не упоминай SQL. Только факты из данных."
)


def build_sql_query(
    messages: list[dict],
    review_prompt: str,
    model_name: str = DEFAULT_MODEL,
) -> str:
    """Генерирует и проверяет SQL-запрос без выполнения в БД.

    Проходит стадии генерации черновика и LLM-ревью, возвращает
    итоговый SQL, готовый к выполнению.

    Args:
        messages: Список сообщений вида {role, content}. Исходный список не мутируется.
        review_prompt: Промпт для второго прохода LLM-проверки SQL.
        model_name: Идентификатор модели на OpenRouter.

    Returns:
        str: Проверенный и отформатированный SQL-запрос,
            либо строка отказа (CANNOT_ANSWER / PROMPT_INJECTION).
    """
    working_messages = [m.copy() for m in messages]

    # Stage 1: генерация чернового SQL
    draft_sql = query_llm(working_messages, model_name, temperature=SQL_TEMPERATURE)
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
    reviewed_sql = query_llm(working_messages, model_name, temperature=SQL_TEMPERATURE)
    reviewed_sql_clean = normalize_llm_sql_response(reviewed_sql)

    if is_cannot_answer(reviewed_sql_clean):
        return CANNOT_ANSWER

    reviewed_sql_clean = _validate_or_cannot_answer(reviewed_sql_clean)
    if is_cannot_answer(reviewed_sql_clean):
        return PROMPT_INJECTION

    return _transpile(reviewed_sql_clean)


_ANSWER_PROMPT_TEMPLATE = (
    "Пользователь спросил: {question}\n\n"
    "Результат SQL-запроса ({row_count} строк):\n{rows_text}\n\n"
    "Сформулируй краткий и понятный ответ на русском языке.\n"
    "Не упоминай SQL. Только факты из данных."
)


def generate_answer(
    question: str,
    sql_result: list[tuple] | str,
    model_name: str = DEFAULT_MODEL,
) -> str:
    """Синтезирует ответ на естественном языке из результата SQL-запроса.

    Args:
        question (str): Исходный вопрос пользователя.
        sql_result (list[tuple] | str): Результат execute_sql_query — список строк или строка
            с ошибкой/отказом.
        model_name (str): Идентификатор модели на OpenRouter.

    Returns:
        str: Ответ на естественном языке либо исходная строка ошибки/отказа.
    """
    if isinstance(sql_result, str):
        return sql_result

    rows_text = "\n".join(str(row) for row in sql_result[:50])
    prompt = _ANSWER_PROMPT_TEMPLATE.format(
        question=question,
        row_count=len(sql_result),
        rows_text=rows_text,
    )
    messages = [{"role": "user", "content": prompt}]
    return query_llm(messages, model_name, temperature=SQL_TEMPERATURE)
