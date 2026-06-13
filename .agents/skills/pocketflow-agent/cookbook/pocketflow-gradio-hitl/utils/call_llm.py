import os

from openai import OpenAI
from openai.types.chat.chat_completion import ChatCompletion

import instructor

api_key = os.getenv("OPENAI_API_KEY")
base_url = "https://api.openai.com/v1"
model = "gpt-4o"


def get_instructor_client():
    """Returns an instructor-patched client."""
    client = OpenAI(api_key=api_key, base_url=base_url)
    return instructor.from_openai(client)


def call_llm(message: str):
    print(f"Calling LLM with message: \n{message}")
    client = OpenAI(api_key=api_key, base_url=base_url)
    response: ChatCompletion = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": message}]
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    print(call_llm("Hello, how are you?"))
