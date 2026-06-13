import os
from typing import Literal, Optional

from pydantic import BaseModel, Field

from pocketflow import Node, StructuredNode


class GeneratorSchema(BaseModel):
    description: str = Field(
        description="The product description, clear, persuasive, and compelling, 2-3 sentences"
    )


class JudgeSchema(BaseModel):
    score: int = Field(
        description="Score on a scale of 1-10 for clarity and persuasiveness"
    )
    reasoning: str = Field(description="Brief explanation of the score")
    verdict: Literal["PASS", "FAIL"] = Field(
        description="Use 'PASS' if score >= 7, otherwise 'FAIL'"
    )
    feedback: Optional[str] = Field(
        default="", description="Specific suggestions for improvement (only if FAIL)"
    )


class Generator(StructuredNode):
    def __init__(self, max_retries=3, wait=10):
        from utils import get_instructor_client

        model = "gpt-4o"
        if os.environ.get("GEMINI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            model = "gemini-2.0-flash"

        super().__init__(
            response_model=GeneratorSchema,
            client=get_instructor_client(),
            model=model,
            max_retries=max_retries,
            wait=wait,
        )

    def prep(self, shared):
        task = shared["task"]
        feedback = shared.get("feedback", "")

        prompt = f"Write a product description for: {task}\n\nThe description should be clear, persuasive, and compelling. Keep it to 2-3 sentences."
        if feedback:
            prompt += f"\n\nPrevious attempt was rejected. Here is the feedback:\n{feedback}\n\nPlease improve based on this feedback."

        return prompt

    def post(self, shared, prep_res, exec_res):
        description = exec_res.description.strip()
        shared["draft"] = description
        print(f"\n✍️  --- Draft (Attempt {shared.get('attempts', 0) + 1}) ---")
        print(description)
        print()


class Judge(StructuredNode):
    def __init__(self, max_retries=3, wait=10):
        from utils import get_instructor_client

        model = "gpt-4o"
        if os.environ.get("GEMINI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            model = "gemini-2.0-flash"

        super().__init__(
            response_model=JudgeSchema,
            client=get_instructor_client(),
            model=model,
            max_retries=max_retries,
            wait=wait,
        )

    def prep(self, shared):
        draft = shared["draft"]
        prompt = f"Rate this product description on a scale of 1-10 for clarity and persuasiveness.\n\nDescription:\n{draft}"
        return prompt

    def post(self, shared, prep_res, exec_res):
        score = exec_res.score
        verdict = exec_res.verdict
        reasoning = exec_res.reasoning.strip()
        feedback = exec_res.feedback.strip() if exec_res.feedback else ""

        print(f"🔍 Judge Score: {score}/10")
        print(f"💡 Reasoning: {reasoning}")

        if verdict.upper() == "PASS" or score >= 7:
            print("✅ PASS - Description accepted!")
            shared["final_description"] = shared["draft"]
            shared["final_score"] = score
            return "pass"

        # Track attempts
        shared["attempts"] = shared.get("attempts", 0) + 1
        shared["feedback"] = feedback if feedback else reasoning

        if shared["attempts"] >= 3:
            print("🤔 Max attempts reached. Accepting current draft.")
            shared["final_description"] = shared["draft"]
            shared["final_score"] = score
            return "pass"

        print(f"❌ FAIL - Sending back for revision (attempt {shared['attempts']}/3)")
        print(f"📝 Feedback: {feedback}")
        return "fail"
