import asyncio
from collections.abc import Callable
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from agent import query_llm, raw_query_llm
from agent.logger import get_logger
from sql_layer import DEFAULT_MODEL, build_messages, query_to_sqllite, sql_validator

log = get_logger("sql_flow")

SYSTEM_PROMPT = (
    "Ты BI аналитик, который на основе запроса делает поиск релевантной информации "
    "и строит отчет саммари. Для поиска информации используй инструменты. "
    "Отвечай только на русском языке."
)

DEFAULT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "sql_layer",
            "description": (
                "Принимает вопрос на естественном языке, генерирует и валидирует "
                "SQL-запрос к строительной БД (VIEW v_construction_data). "
                "Возвращает готовый SQL, статус выполнения и (опционально) строки результата. "
                "Используется для аналитики: объёмы работ, подрядчики, бюджеты, прогресс, "
                "сравнение план/факт по городам, объектам и типам работ."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_question": {
                        "type": "string",
                        "description": (
                            "Вопрос пользователя на естественном языке."
                            "Должен в точности соответсвовать user_query из messages."
                        ),
                    },
                    "model_name": {
                        "type": "string",
                        "description": (
                            "Идентификатор модели на OpenRouter "
                            "(default: 'meta-llama/llama-3.3-70b-instruct')."
                        ),
                    },
                },
                "required": ["user_question"],
            },
        },
    }
]


async def sql_layer(**kwargs) -> str:
    """Инструмент: преобразует вопрос на естественном языке в SQL и возвращает результат.

    Args:
        user_question: Вопрос пользователя.
        model_name: Идентификатор модели (опционально).

    Returns:
        Строка с результатом SQL-запроса или сообщение об ошибке.
    """
    db_dir = Path.cwd().parent.parent / "data" / "db"
    if db_dir.is_dir():
        log.info("База данных определена по адресу: %s", db_dir)
        db_files = sorted(db_dir.glob("construction*.db"))
        if not db_files:
            raise FileNotFoundError(f"Файл базы данных не найден в {db_dir}")
        db_path = db_files[0]
        if db_path.is_file():
            async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        else:
            raise FileNotFoundError(f"Файл базы данных не определен: {db_path}")
    else:
        raise FileNotFoundError(f"Директория базы данных не определена: {db_dir}")

    user_query = kwargs["user_question"]
    log.info("Получен вопрос: %s", user_query)

    messages = await build_messages(user_query, async_engine)
    log.info("Сообщения для валидации сформированы")

    for i in range(3):
        log.info("Попытка валидации SQL #%d/3", i + 1)
        log.debug("Валидация сообщения: %s", messages[-1])
        sql_query = await sql_validator(messages)
        log.info(
            "Статус валидации: %s. Причина остановки: %s.",
            sql_query["status"],
            sql_query["answer"],
        )
        if sql_query["status"] == "ok":
            break
        messages.append(
            {
                "role": "assistant",
                "content": sql_query.get("sql") or sql_query["answer"],
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Предыдущий SQL-запрос вернул статус «{sql_query['status']}» "
                    f"с причиной: {sql_query['answer']}. "
                    "Пожалуйста, исправь запрос или переформулируй его."
                ),
            }
        )
        if i == 2:
            msg = (
                "Запрос не прошел валидацию и вернул следующее,\n"
                + f"Статус запроса: {sql_query['status']}\n"
                + f"Причина остановки: {sql_query['answer']}.\n"
                + "Проверьте корректность запроса или попробуйте его переформулировать."
            )
            log.warning("Валидация не пройдена: %s", sql_query["answer"])
            return msg

    log.info("SQL-запрос:\n%s", sql_query["sql"])
    db_result = await query_to_sqllite(sql_query["sql"])
    log.info("Получено строк из БД: %d", len(db_result) - 1)
    return db_result


DEFAULT_TOOL_MAPPING: dict[str, Callable] = {"sql_layer": sql_layer}


async def execute_tool_calls(
    tool_calls: list, tool_mapping: dict[str, Callable]
) -> list[dict]:
    """Обрабатывает список tool_calls от LLM и возвращает сообщения для истории.

    Для каждого tool_call:
    1. Добавляет assistant-сообщение с tool_calls
    2. Вызывает соответствующую функцию из tool_mapping через await + **
    3. Добавляет tool-сообщение с результатом
    4. При ошибке — user-сообщение с описанием ошибки

    Args:
        tool_calls: Список tool_calls из ответа LLM.
        tool_mapping: Маппинг {имя_функции: callable}.

    Returns:
        Список сообщений (assistant + tool/error) для добавления в messages.
    """
    log.info("Обработка %d tool_call(s)", len(tool_calls))
    tool_messages = []
    for idx, tool in enumerate(tool_calls, 1):
        try:
            func_id = tool.id
            func_arguments = json.loads(tool.function.arguments)
            func_name = tool.function.name
            log.info("#%d: %s(%s)", idx, func_name, func_arguments)
            if func_name not in tool_mapping:
                log.warning("#%d: %s — неизвестная функция", idx, func_name)
                tool_messages.append(
                    {
                        "role": "tool",
                        "content": f"Неизвестная функция: {func_name}",
                        "tool_call_id": func_id,
                    }
                )
                continue

            tool_messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": func_id,
                            "type": "function",
                            "function": {
                                "name": func_name,
                                "arguments": str(func_arguments),
                            },
                        }
                    ],
                }
            )

            try:
                log.info("Начало выполнения функции #%d: %s", idx, func_name)
                func_result = await tool_mapping[func_name](**func_arguments)
                log.info("#%d: %s выполнена успешно", idx, func_name)

                tool_messages.append(
                    {
                        "role": "tool",
                        "content": str(func_result),
                        "tool_call_id": func_id,
                    }
                )
            except Exception as err:
                log.error("#%d: %s — ошибка: %s", idx, func_name, err)
                tool_messages.append(
                    {
                        "role": "tool",
                        "content": f"Ошибка при вызове {func_name}: {err}",
                        "tool_call_id": func_id,
                    }
                )
        except Exception as err:
            log.error("Ошибка при разборе tool_call: %s", err)
            tool_messages.append(
                {
                    "role": "tool",
                    "content": f"Ошибка при разборе tool_call: {err}",
                }
            )

    return tool_messages


async def run_sql_flow(
    user_query: str,
    model_name: str = DEFAULT_MODEL,
    tools: list[dict] = DEFAULT_TOOLS,
    tool_mapping: dict[str, Callable] = DEFAULT_TOOL_MAPPING,
    max_iterations: int = 2,
) -> str:
    """Основная функция LLM-флоу: запрос → tool calls → итоговый ответ.

    Args:
        user_query: Запрос пользователя на естественном языке.
        model_name: Идентификатор модели LLM.
        tools: Список схем инструментов для OpenAI API.
        tool_mapping: Маппинг {имя_функции: callable}.
        max_iterations: Максимум итераций цикла tool calls.

    Returns:
        Текст итогового ответа от LLM.
    """
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_query,
        },
    ]

    for i in range(max_iterations):
        log.info("Итерация #%d/%d — запрос к LLM...", i + 1, max_iterations)
        result = await raw_query_llm(messages, model_name, tools)
        tool_calls = result.choices[0].message.tool_calls
        if tool_calls:
            log.info("LLM вернул %d tool_call(s)", len(tool_calls))
            messages.extend(await execute_tool_calls(tool_calls, tool_mapping))
        else:
            log.info("LLM не вызвал инструменты — выход из цикла")
            break

    log.info("Запрос саммари-ответа от LLM...")
    messages.extend(
        [
            {
                "role": "user",
                "content": "Сформируй краткий ответ на запрос пользователя, на основе полученной ранее информации."
                "При формировании краткого ответа учитывай все колонки из базы данных."
                "Результат должен быть оформлен в виде Markdown таблицы с форматированием по ширине."
                "Если логически запрос пользователя можно разделить на несколько подзапросов, то результат раздели на несколько таблиц."
                "После таблиц обязательно должен присутствовать вывод основанный на запросе, с кратким саммари данных из таблиц.",
            }
        ]
    )

    final_answer = await query_llm(messages=messages, model_name=DEFAULT_MODEL)
    log.info(
        f"\n{60 * '='}\nНа запрос:\n{60 * '='}\n{user_query}\n{60 * '='}\nПолучен ответ:\n{60 * '='}\n{final_answer}\n{60 * '='}\n"
    )
    return final_answer


if __name__ == "__main__":
    user_query = (
        # "Мне нужна инофрмация какие работы сейчас выполняет подрядчик Техстрой, а также их % готовности."
        # "Дополнительно выведи информацию на каких объектах работает Техстрой."
        "На каких объектах работают ПАО МегаСтрой и ООО Новый Век?"
    )
    print(asyncio.run(run_sql_flow(user_query)))
