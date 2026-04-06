import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

openrouter_api_key = os.getenv("OPEN_ROUTE_API_KEY")
if not openrouter_api_key:
    raise ValueError("OPEN_ROUTE_API_KEY environment variable not set.")


def query_llm(messages: list[dict]) -> str:
    """
    Queries the LLM with the provided messages and returns the response.

    Args:
        messages (list[dict]): A list of messages to send to the LLM.
            Example:
            [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is the capital of France?"}
            ]

    Returns:
        str: The response from the LLM.
    """
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=openrouter_api_key,
    )

    if not messages:
        raise ValueError("LLM messages cannot be empty")

    completion = client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct",
        messages=messages,
    )

    return completion.choices[0].message.content


def raw_query_llm(messages: list[dict]) -> str:
    """
    Queries the LLM with the provided messages and returns the raw response without any processing.

    Args:
        messages (list[dict]): A list of messages to send to the LLM.
            Example:
            [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is the capital of France?"}
            ]

    Returns:
        str: The raw response from the LLM.
    """
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=openrouter_api_key,
    )

    if not messages:
        raise ValueError("LLM messages cannot be empty")

    completion = client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct",
        messages=messages,
        extra_body={
            "provider": {
                "sort": "price",
            }
        },
    )

    return completion
