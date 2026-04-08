import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


openrouter_api_key = os.getenv("OPEN_ROUTE_API_KEY")
if not openrouter_api_key:
    raise ValueError("OPEN_ROUTE_API_KEY environment variable not set.")


def query_llm(query: str):
    """Отправляет одиночный пользовательский запрос в LLM и возвращает ответ.

    Args:
        query (str): Текст запроса, который будет передан модели как user-сообщение.

    Returns:
        str: Текстовый ответ модели.
    """
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=openrouter_api_key,
    )

    completion = client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct",
        messages=[{"role": "user", "content": query}],
    )
    return completion.choices[0].message.content
