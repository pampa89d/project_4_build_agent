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
    messages: list[dict], model_name: str, temperature: float = 0.0
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

    completion = await async_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=temperature,
    )

    return completion.choices[0].message.content


async def raw_query_llm(
    messages: list[dict], model_name: str, temperature: float = 0.0
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

    completion = await async_client.chat.completions.create(
        model=model_name,
        messages=messages,
        extra_body={
            "provider": {
                "sort": "price",
            }
        },
        temperature=temperature,
    )

    return completion
