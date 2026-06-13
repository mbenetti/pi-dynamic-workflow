import os

from openai import OpenAI

import instructor


def get_instructor_client():
    """Returns an instructor-patched client."""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))
    return instructor.from_openai(client)


def call_llm(prompt):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))
    r = client.chat.completions.create(
        model="gpt-4o", messages=[{"role": "user", "content": prompt}]
    )
    return r.choices[0].message.content


if __name__ == "__main__":
    print(call_llm("Tell me a short joke"))
