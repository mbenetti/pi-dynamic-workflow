import os

from openai import OpenAI

import instructor


def call_llm(prompt):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))
    r = client.chat.completions.create(
        model="gpt-4o", messages=[{"role": "user", "content": prompt}]
    )
    return r.choices[0].message.content


def get_instructor_client():
    return instructor.from_openai(
        OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))
    )


# Example usage
if __name__ == "__main__":
    print(call_llm("Tell me a short joke"))
