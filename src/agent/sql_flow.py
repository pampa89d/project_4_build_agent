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

from sqlalchemy.ext.asyncio import AsyncEngine

from src.agent.llm_client import async_client, query_llm
from src.sql_layer.pipeline import (
    CANNOT_ANSWER,
    PROMPT_INJECTION,
    DEFAULT_MODEL,
    SQL_TEMPERATURE,
    generate_answer,
    validate_safe_sql,
    normalize_llm_sql_response,
    is_cannot_answer,
)
from src.sql_layer.prompts import build_messages

# Максимальное количество итераций агентского цикла
# (tool call -> execution -> response).
# Предотвращает бесконечный цикл при некорректном поведении модели.
MAX_ITERATIONS = 3

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
                    "description": "SQL-запрос (SELECT) к базе данных строительства.",
                },
            },
            "required": ["sql_query"],
        },
    },
}


class AgentFlow:
    """Оркестратор LLM-пайплайна через tool calling для ответов на вопросы пользователя.

    Использует паттерн agent loop:
    1. LLM получает системный промпт с контекстом схемы БД и вопрос пользователя.
    2. LLM решает, нужно ли вызвать execute_sql tool.
    3. Если LLM вызывает tool — агент исполняет SQL и возвращает результат.
    4. LLM формирует финальный ответ на основе данных.
    5. Цикл повторяется, пока LLM не вернёт текстовый ответ без tool call.

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
    # Инструменты (tools), доступные LLM
    # ------------------------------------------------------------------

    async def _tool_execute_sql(self, sql_query: str) -> str:
        """Исполняет SQL-запрос из tool call и возвращает сериализованный результат.

        Выполняет валидацию SQL (только SELECT), затем исполняет запрос
        через SQLAlchemy и возвращает результат как JSON-строку.
        При ошибке возвращает JSON с описанием ошибки для обратной связи LLM.

        Args:
            sql_query (str): SQL-запрос, сгенерированный LLM через tool call.

        Returns:
            str: JSON-строка с ключами:
                - status ("success" | "error" | "refusal"): статус выполнения.
                - rows (list[list]): строки результата при успехе.
                - row_count (int): количество строк при успехе.
                - error (str): описание ошибки
                    при статусе "error".
                - message (str): причина отказа
                    при статусе "refusal".
        """
        # TODO: нормализация ответа через normalize_llm_sql_response
        # TODO: проверка на отказ (is_cannot_answer)
        # TODO: валидация безопасности через validate_safe_sql
        # TODO: выполнение SQL через engine.connect() + conn.execute(text(sql))
        # TODO: сериализация результата в JSON с ключами status, rows, row_count
        # TODO: обработка ошибок — возврат JSON с status="error" и описанием
        pass

    # ------------------------------------------------------------------
    # Реестр инструментов: связывает имя tool с методом-обработчиком
    # ------------------------------------------------------------------

    def _get_tool_handlers(self) -> dict[str, callable]:
        """Возвращает словарь соответствия имён tools и методов агента.

        Returns:
            dict[str, callable]: Маппинг имени tool -> async-функция обработчик.
        """
        return {
            "execute_sql": self._tool_execute_sql,
        }

    # ------------------------------------------------------------------
    # Основной агентский цикл
    # ------------------------------------------------------------------

    async def ask(self, question: str) -> dict:
        """Обрабатывает вопрос пользователя через агентский цикл с tool calling.

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
                - answer (str): Ответ на естественном языке или сообщение об ошибке.
                - status (str): Статус — "ok" | "cannot_answer" | "error".
                - sql_rows_count (int | None): Количество строк
                    результата SQL, None при ошибке или отказе.
        """
        # TODO: сборка сообщений через build_messages(question, self.engine)
        # TODO: получение реестра tools через _get_tool_handlers()
        # TODO: цикл до MAX_ITERATIONS:
        #     - вызов async_client.chat.completions.create с tools=[SQL_TOOL_DEFINITION]
        #     - проверка ответа: есть ли tool_calls в choice.message
        #     - если tool_calls: извлечение имени и аргументов,
        #       вызов соответствующего обработчика из реестра,
        #       добавление tool message в историю,
        #       продолжение цикла
        #     - если нет tool_calls (текстовый ответ): выход из цикла
        # TODO: формирование dict-результата на основе финального ответа LLM
        pass

    async def ask_sql_only(self, question: str) -> str:
        """Генерирует SQL-запрос по вопросу пользователя без выполнения в БД.

        Вызывает LLM с tool execute_sql, но вместо реального выполнения
        извлекает SQL из первого tool call и возвращает его.

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
        # TODO: если LLM вернула tool_call с execute_sql — извлечь sql_query из аргументов
        # TODO: если LLM вернула текст без tool_call — вернуть как есть (возможно отказ)
        pass
