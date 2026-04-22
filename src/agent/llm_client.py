import os

from dotenv import load_dotenv
from openai import AsyncOpenAI, APIStatusError, APIConnectionError

from agent.logger import get_logger

load_dotenv()

openrouter_api_key = os.getenv("OPEN_ROUTE_API_KEY")
if not openrouter_api_key:
    raise ValueError("OPEN_ROUTE_API_KEY environment variable not set.")

async_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=openrouter_api_key,
)

log = get_logger("llm_client")


async def query_llm(
    messages: list[dict],
    model_name: str,
    tools: list = None,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> str:
    """Отправляет список сообщений в LLM и возвращает текст ответа.

    Args:
        messages (list[dict]): Список сообщений в формате chat completion.
        model_name (str): Имя модели, которая будет вызвана через OpenRouter.
        temperature (float): Температура генерации. По умолчанию 0.0.
        max_tokens (int): Максимум токенов в ответе. По умолчанию 2048.

    Returns:
        str: Текстовое содержимое ответа модели.
    """
    if not messages:
        raise ValueError("LLM messages cannot be empty")

    if not tools:
        tools = []

    log.debug(
        "model=%s, messages=%d, tools=%d",
        model_name, len(messages), len(tools),
    )
    try:
        completion = await async_client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except APIStatusError as err:
        log.error(
            "API error %s: status=%d, body=%s",
            type(err).__name__, err.status_code, err.message,
        )
        raise
    except APIConnectionError as err:
        log.error("Connection error: %s", err)
        raise

    content = completion.choices[0].message.content
    log.debug("ответ: %r", content)
    return content


async def raw_query_llm(
    messages: list[dict],
    model_name: str,
    tools: list = None,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> str:
    """Отправляет список сообщений в LLM и возвращает сырой объект ответа.

    Args:
        messages (list[dict]): Список сообщений в формате chat completion.
        model_name (str): Имя модели, которая будет вызвана через OpenRouter.
        temperature (float): Температура генерации. По умолчанию 0.0.
        max_tokens (int): Максимум токенов в ответе. По умолчанию 2048.

    Returns:
        str: Сырой ответ клиента OpenAI без дополнительной постобработки.
    """
    if not messages:
        raise ValueError("LLM messages cannot be empty")

    if not tools:
        tools = []

    log.debug(
        "model=%s, messages=%d, tools=%d",
        model_name, len(messages), len(tools),
    )
    try:
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
            max_tokens=max_tokens,
        )
    except APIStatusError as err:
        log.error(
            "API error %s: status=%d, body=%s",
            type(err).__name__, err.status_code, err.message,
        )
        raise
    except APIConnectionError as err:
        log.error("Connection error: %s", err)
        raise

    msg = completion.choices[0].message
    log.debug(
        "content=%r, tool_calls=%d",
        msg.content, len(msg.tool_calls) if msg.tool_calls else 0,
    )
    return completion
