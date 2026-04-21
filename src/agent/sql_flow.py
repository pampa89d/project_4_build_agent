import asyncio
from collections.abc import Callable
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from agent import query_llm, raw_query_llm
from sql_layer import DEFAULT_MODEL, build_messages, query_to_sqllite, sql_validator

SYSTEM_PROMPT = (
    "Ты BI аналитик, который на основе запроса делает поиск релевантной информации "
    "и строит отчет саммари. Для поиска информации используй инструменты."
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
                        "description": ("Вопрос пользователя на естественном языке."),
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
    # TODO: реализация
    # - извлечь user_question из kwargs
    # - вызвать build_messages(user_question, async_engine)
    # - цикл до 3 попыток: sql_validator(messages)
    # - при status == "ok": query_to_sqllite(sql) → str(result)
    # - при неудаче: вернуть сообщение об ошибке
    db_dir = Path.cwd().parent.parent / "data" / "db"
    if db_dir.is_dir():
        print(f"[sql_layer] База данных определена по адресу: {db_dir}")
        db_files = sorted(db_dir.glob("construction*.db"))
        if not db_files:
            raise FileNotFoundError(
                f"[sql_layer] Файл базы данных не найден в {db_dir}"
            )
        db_path = db_files[0]
        if db_path.is_file():
            async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        else:
            raise FileNotFoundError(
                f"[sql_layer] Файл базы данных не определен: {db_path}"
            )
    else:
        raise FileNotFoundError(
            f"[sql_layer] Директория базы данных не определена: {db_dir}"
        )

    user_query = kwargs["user_question"]
    print(f"[sql_layer] Получен вопрос: {user_query}")

    messages = await build_messages(user_query, async_engine)
    print("[sql_layer] Сообщения для валидации сформированы")

    for i in range(3):
        print(f"[sql_layer] Попытка валидации SQL #{i + 1}/3")
        sql_query = await sql_validator(messages)
        print(
            f"[sql_layer] Статус валидации: {sql_query['status']}.\nПричина остановки: {sql_query['answer']}."
        )
        if sql_query["status"] == "ok":
            break
        if i == 2:
            msg = (
                "Запрос не прошел валидацию и вернул следующее,\n"
                + f"Статус запроса: {sql_query['status']}\n"
                + f"Причина остановки: {sql_query['answer']}.\n"
                + "Проверьте корректность запроса или попробуйте его переформулировать."
            )
            print(f"[sql_layer] Валидация не пройдена: {sql_query['answer']}")
            return msg

    print(f"[sql_layer] SQL-запрос:\n{sql_query['sql']}")
    db_result = await query_to_sqllite(sql_query["sql"])
    print(f"[sql_layer] Получено строк из БД: {len(db_result) - 1}")
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
    # TODO: реализация
    # - для каждого tool_call:
    #   - сформировать assistant-сообщение с tool_calls
    #   - распаковать arguments через json.loads + **kwargs
    #   - вызвать await tool_mapping[name](**args)
    #   - при успехе: tool-сообщение с str(result)
    #   - при ошибке: user-сообщение с описанием ошибки
    print(f"[execute_tool_calls] Обработка {len(tool_calls)} tool_call(s)")
    tool_messages = []
    for idx, tool in enumerate(tool_calls, 1):
        try:
            func_id = tool.id
            func_arguments = json.loads(tool.function.arguments)
            func_name = tool.function.name
            print(f"[execute_tool_calls] #{idx}: {func_name}({func_arguments})")
            if func_name not in tool_mapping:
                print(f"[execute_tool_calls] #{idx}: {func_name} — неизвестная функция")
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
                func_result = await tool_mapping[func_name](**func_arguments)
                print(f"[execute_tool_calls] #{idx}: {func_name} выполнена успешно")

                tool_messages.append(
                    {
                        "role": "tool",
                        "content": str(func_result),
                        "tool_call_id": func_id,
                    }
                )
            except Exception as err:
                print(f"[execute_tool_calls] #{idx}: {func_name} — ошибка: {err}")
                tool_messages.append(
                    {
                        "role": "tool",
                        "content": f"Ошибка при вызове {func_name}: {err}",
                        "tool_call_id": func_id,
                    }
                )
        except Exception as err:
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
    # TODO: реализация
    # - инициализация messages с SYSTEM_PROMPT + user_query
    # - defaults: tools=DEFAULT_TOOLS, tool_mapping=DEFAULT_TOOL_MAPPING
    # - цикл до max_iterations:
    #   1. raw_query_llm(messages, model_name, tools)
    #   2. если есть tool_calls → execute_tool_calls → добавить в messages
    #   3. если нет tool_calls → break
    # - финальный вызов query_llm с запросом на саммари
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
        print(f"[run_sql_flow] Итерация #{i + 1}/{max_iterations} — запрос к LLM...")
        result = await raw_query_llm(messages, model_name, tools=tools)
        tool_calls = result.choices[0].message.tool_calls
        if tool_calls:
            print(f"[run_sql_flow] LLM вернул {len(tool_calls)} tool_call(s)")
            messages.extend(await execute_tool_calls(tool_calls, tool_mapping))
        else:
            print("[run_sql_flow] LLM не вызвал инструменты — выход из цикла")
            break

    print("[run_sql_flow] Запрос саммари-ответа от LLM...")
    messages.extend(
        [
            {
                "role": "user",
                "content": "Сформируй краткий ответ на запрос пользователя, на основе полученной ранее информации.",
            }
        ]
    )

    final_answer = await query_llm(messages=messages, model_name=DEFAULT_MODEL)
    print("[run_sql_flow] Ответ получен")
    return final_answer


user_query = "Мне нужна инофрмация какие работы сейчас выполняет подрядчик Строймонтаж, а также их % готовности."

print(asyncio.run(run_sql_flow(user_query)))
