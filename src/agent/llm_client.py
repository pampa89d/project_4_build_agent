import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

openrouter_api_key = os.getenv("OPEN_ROUTE_API_KEY")
if not openrouter_api_key:
    raise ValueError("OPEN_ROUTE_API_KEY environment variable not set.")

async_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=openrouter_api_key,
)


async def query_llm(
    messages: list[dict], model_name: str, tools: list = None, temperature: float = 0.0
) -> str:
    """Отправляет список сообщений в LLM и возвращает текст ответа.

    Args:
        messages (list[dict]): Список сообщений в формате chat completion.
            Каждый элемент должен содержать ключи role и content.
        model_name (str): Имя модели, которая будет вызвана через OpenRouter.
        temperature (float): Температура генерации. По умолчанию 0.0.

    Returns:
        str: Текстовое содержимое ответа модели.
    """
    if not messages:
        raise ValueError("LLM messages cannot be empty")

    if not tools:
        tools = []

    print(
        f"[query_llm] model={model_name}, "
        f"messages={len(messages)}, tools={len(tools)}"
    )
    completion = await async_client.chat.completions.create(
        model=model_name,
        messages=messages,
        tools=tools,
        temperature=temperature,
    )
    content = completion.choices[0].message.content
    print(f"[query_llm] ответ: {content!r}")
    return content


async def raw_query_llm(
    messages: list[dict], model_name: str, tools: list = None, temperature: float = 0.0
) -> str:
    """Отправляет список сообщений в LLM и возвращает сырой объект ответа.

    Args:
        messages (list[dict]): Список сообщений в формате chat completion.
        model_name (str): Имя модели, которая будет вызвана через OpenRouter.
        temperature (float): Температура генерации. По умолчанию 0.0.

    Returns:
        str: Сырой ответ клиента OpenAI без дополнительной постобработки.
    """
    if not messages:
        raise ValueError("LLM messages cannot be empty")

    if not tools:
        tools = []

    print(
        f"[raw_query_llm] model={model_name}, "
        f"messages={len(messages)}, tools={len(tools)}"
    )
    completion = await async_client.chat.completions.create(
        model=model_name,
        messages=messages,
        tools=tools,
        extra_body={
            "provider": {
                "sort": "price",
            }
        },
        temperature=temperature,
    )
    msg = completion.choices[0].message
    print(
        f"[raw_query_llm] content={msg.content!r}, "
        f"tool_calls={len(msg.tool_calls) if msg.tool_calls else 0}"
    )
    return completion
