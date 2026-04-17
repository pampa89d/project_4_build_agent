"""LLM flow-агент для оркестрации text-to-SQL пайплайна через tool calling.

Агент использует tool-use (function calling) LLM:
1. Отправляет вопрос пользователя + схему БД в LLM с доступным tool execute_sql.
2. LLM решает, вызывать ли tool и с каким SQL.
3. Агент исполняет SQL через sql_layer, возвращает результат в LLM.
4. LLM формирует финальный ответ на естественном языке.

На текущем шаге реализован только SQL-слой (text-to-SQL).
В дальнейшем будет расширен RAG-слоем и другими модулями.
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.agent.llm_client import async_client, query_llm
from src.sql_layer.pipeline import (
    CANNOT_ANSWER,
    PROMPT_INJECTION,
    DEFAULT_MODEL,
    SQL_TEMPERATURE,
    normalize_llm_sql_response,
    is_cannot_answer,
    validate_safe_sql,
)
from src.sql_layer.prompts import REVIEW_PROMPT, build_messages

# Максимальное количество итераций агентского цикла
# (tool call -> execution -> response).
# Предотвращает бесконечный цикл при некорректном поведении модели.
MAX_ITERATIONS = 3

# Количество попыток выполнения SQL при ошибке.
MAX_SQL_RETRIES = 3

# Промпт для LLM при ошибке выполнения SQL.
_ERROR_FIX_PROMPT_TEMPLATE = (
    "Предыдущий SQL-запрос вызвал ошибку выполнения: {error}. "
    "Исправь SQL-запрос так, чтобы он соответствовал SYSTEM_PROMPT. "
    "Проверь валидность фильтрации, works.unit при агрегации "
    "объемов, отсутствие progress.unit и отсутствие даты без "
    "явного запроса пользователя. Если корректный SQL построить "
    "нельзя, верни ровно: Невозможно ответить. Верни ровно один "
    "исправленный SQL-запрос без объяснений, без markdown, без "
    "комментариев и без лишнего текста."
)

# Определение tool для OpenAI-совместимого API.
# LLM будет вызывать execute_sql с параметром sql_query.
SQL_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "execute_sql",
        "description": (
            "Выполняет SQL-запрос к базе данных строительства "
            "и возвращает результат. Используй этот tool, когда "
            "нужно получить данные из БД для ответа на вопрос "
            "пользователя. Запрос должен быть корректным SQL "
            "(SQLite диалект) и использовать только SELECT."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql_query": {
                    "type": "string",
                    "description": (
                        "SQL-запрос (SELECT) к базе данных "
                        "строительства."
                    ),
                },
            },
            "required": ["sql_query"],
        },
    },
}


class AgentFlow:
    """Оркестратор LLM-пайплайна через tool calling для ответов на вопросы пользователя.

    Использует паттерн agent loop:
    1. LLM получает системный промпт с контекстом схемы БД
       и вопрос пользователя.
    2. LLM решает, нужно ли вызвать execute_sql tool.
    3. Если LLM вызывает tool — агент исполняет SQL
       и возвращает результат.
    4. LLM формирует финальный ответ на основе данных.
    5. Цикл повторяется, пока LLM не вернёт текстовый
       ответ без tool call.

    Attributes:
        engine (AsyncEngine): SQLAlchemy-движок для подключения к БД.
        model_name (str): Идентификатор модели LLM на OpenRouter.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        model_name: str = DEFAULT_MODEL,
    ) -> None:
        """Инициализирует агент с подключением к БД и параметрами модели.

        Args:
            engine: SQLAlchemy AsyncEngine для выполнения SQL-запросов.
            model_name: Идентификатор модели на OpenRouter.
                По умолчанию используется DEFAULT_MODEL из sql_layer.
        """
        # TODO: сохранить engine и model_name как атрибуты экземпляра

    # ------------------------------------------------------------------
    # Выполнение SQL с retry-loop (вынесено из sql_layer/pipeline.py)
    # ------------------------------------------------------------------

    async def _execute_sql_with_retry(
        self,
        sql: str,
        messages: list[dict],
    ) -> list[tuple] | str:
        """Выполняет SQL с циклом повторных попыток при ошибках.

        Цикл до MAX_SQL_RETRIES:
        1. Попытка выполнить sql через engine.
        2. При ошибке — отправка ошибки в LLM для исправления SQL.
        3. Новая попытка с исправленным SQL.
        4. При исчерпании попыток — возврат строки ошибки.

        Вся история (ошибки + исправленные SQL) накапливается
        в messages, чтобы LLM видел контекст всех попыток.

        Args:
            sql (str): SQL-запрос для выполнения (уже отвалидированный).
            messages (list[dict]): История сообщений чата. Мутируется —
                в неё добавляются пары assistant/user с ошибками
                и исправлениями. Используется для передачи контекста
                в LLM при каждой попытке исправления.

        Returns:
            list[tuple] | str: Результат SQL при успехе,
                либо строка ошибки/отказа.
        """
        # TODO: цикл for attempt в range(1, MAX_SQL_RETRIES + 1):
        #     - выполнить sql через engine.connect() + conn.execute(text(sql))
        #     - при успехе: вернуть result.fetchall()
        #     - при ошибке:
        #         - если последняя попытка: вернуть строку ошибки
        #         - добавить в messages:
        #             assistant: текущий sql
        #             user: промпт _ERROR_FIX_PROMPT_TEMPLATE.format(error=err)
        #         - вызвать query_llm для исправления SQL
        #         - normalize + validate исправленного SQL
        #         - при отказе LLM: вернуть CANNOT_ANSWER / PROMPT_INJECTION
        #         - обновить sql для следующей итерации
        pass

    # ------------------------------------------------------------------
    # Инструменты (tools), доступные LLM
    # ------------------------------------------------------------------

    async def _tool_execute_sql(
        self,
        sql_query: str,
        messages: list[dict],
    ) -> str:
        """Исполняет SQL-запрос из tool call и возвращает
        сериализованный результат.

        Выполняет валидацию SQL (только SELECT), затем запускает
        retry-loop через _execute_sql_with_retry и возвращает
        результат как JSON-строку.
        При ошибке возвращает JSON с описанием ошибки для обратной
        связи LLM.

        Args:
            sql_query (str): SQL-запрос, сгенерированный LLM
                через tool call.
            messages (list[dict]): История сообщений чата.
                Передаётся в _execute_sql_with_retry для retry-loop.

        Returns:
            str: JSON-строка с ключами:
                - status ("success" | "error" | "refusal"):
                    статус выполнения.
                - rows (list[list]): строки результата при успехе.
                - row_count (int): количество строк при успехе.
                - error (str): описание ошибки
                    при статусе "error".
                - message (str): причина отказа
                    при статусе "refusal".
        """
        # TODO: нормализация через normalize_llm_sql_response
        # TODO: проверка на отказ (is_cannot_answer)
        # TODO: валидация безопасности через validate_safe_sql
        #   - при ошибке валидации: возврат JSON {status: "error", error: ...}
        # TODO: вызов _execute_sql_with_retry(sql, messages)
        # TODO: при isSuccess — сериализация rows в JSON:
        #   {status: "success", rows: [...], row_count: N}
        # TODO: при отказе/ошибке — JSON с соответствующим статусом
        pass

    # ------------------------------------------------------------------
    # Реестр инструментов: связывает имя tool с методом-обработчиком
    # ------------------------------------------------------------------

    def _get_tool_handlers(self) -> dict[str, callable]:
        """Возвращает словарь соответствия имён tools и методов агента.

        Returns:
            dict[str, callable]: Маппинг имени tool
                -> async-функция обработчик.
        """
        return {
            "execute_sql": self._tool_execute_sql,
        }

    # ------------------------------------------------------------------
    # Основной агентский цикл
    # ------------------------------------------------------------------

    async def ask(self, question: str) -> dict:
        """Обрабатывает вопрос пользователя через агентский цикл
        с tool calling.

        Цикл:
        1. Сборка сообщений (system prompt + user question).
        2. Вызов LLM с привязанным tool execute_sql.
        3. Если LLM возвращает tool_call — исполнение tool,
           добавление результата в сообщения, повторный вызов LLM.
        4. Если LLM возвращает текст — это финальный ответ.

        Args:
            question (str): Вопрос пользователя на естественном языке.

        Returns:
            dict: Словарь с ключами:
                - answer (str): Ответ на естественном языке
                    или сообщение об ошибке.
                - status (str): Статус —
                    "ok" | "cannot_answer" | "error".
                - sql_rows_count (int | None): Количество строк
                    результата SQL, None при ошибке или отказе.
        """
        # TODO: сборка сообщений через build_messages(question, self.engine)
        # TODO: получение реестра tools через _get_tool_handlers()
        # TODO: цикл до MAX_ITERATIONS:
        #     - вызов async_client.chat.completions.create
        #       с tools=[SQL_TOOL_DEFINITION]
        #     - проверка ответа: есть ли tool_calls в choice.message
        #     - если tool_calls:
        #         извлечение имени и аргументов,
        #         вызов соответствующего обработчика из реестра
        #           (передавая messages для retry-loop),
        #         добавление tool message в историю,
        #         продолжение цикла
        #     - если нет tool_calls (текстовый ответ):
        #         выход из цикла
        # TODO: формирование dict-результата на основе
        #   финального ответа LLM
        pass

    async def ask_sql_only(self, question: str) -> str:
        """Генерирует SQL-запрос по вопросу пользователя
        без выполнения в БД.

        Вызывает LLM с tool execute_sql, но вместо реального
        выполнения извлекает SQL из первого tool call и возвращает его.

        Полезно для отладки и предпросмотра сгенерированного SQL.

        Args:
            question (str): Вопрос пользователя на естественном языке.

        Returns:
            str: SQL-запрос, сгенерированный LLM через tool call,
                либо строка отказа (CANNOT_ANSWER / PROMPT_INJECTION),
                либо текстовый ответ LLM, если tool не был вызван.
        """
        # TODO: сборка сообщений через build_messages(question, self.engine)
        # TODO: вызов LLM с tools=[SQL_TOOL_DEFINITION]
        # TODO: если LLM вернула tool_call с execute_sql —
        #   извлечь sql_query из аргументов
        # TODO: если LLM вернула текст без tool_call —
        #   вернуть как есть (возможно отказ)
        pass
