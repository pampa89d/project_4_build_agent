import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


openrouter_api_key = os.getenv("OPEN_ROUTE_API_KEY")
if not openrouter_api_key:
    raise ValueError("OPEN_ROUTE_API_KEY environment variable not set.")


def query_llm(query: str):
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=openrouter_api_key,
    )

    completion = client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct",
        messages=[
            {
                "role": "user",
                "content": query
            }
        ]
    )
    return completion.choices[0].message.content
