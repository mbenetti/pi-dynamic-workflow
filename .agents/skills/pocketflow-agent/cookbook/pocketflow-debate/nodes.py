from typing import Literal

from pydantic import BaseModel, Field

from pocketflow import StructuredNode


class AdvocateResponse(BaseModel):
    argument: str = Field(description="The strongest case/argument in 3-4 sentences.")
    key_points: list[str] = Field(description="List of 3 key points.")


class JudgeResponse(BaseModel):
    winner: Literal["FOR", "AGAINST"] = Field(
        description="Which argument is stronger? Must be 'FOR' or 'AGAINST'."
    )
    score_for: int = Field(description="Score for the FOR argument, from 1 to 10.")
    score_against: int = Field(
        description="Score for the AGAINST argument, from 1 to 10."
    )
    verdict: str = Field(description="One-sentence explanation of the decision.")
    reasoning: str = Field(
        description="Brief analysis of both arguments' strengths and weaknesses."
    )


class AdvocateFor(StructuredNode):
    def __init__(self):
        from utils import get_instructor_client, get_model_name

        super().__init__(
            response_model=AdvocateResponse,
            client=get_instructor_client(),
            model=get_model_name(),
        )

    def prep(self, shared):
        claim = shared["claim"]
        return f"""You are an expert advocate arguing FOR this claim. Be specific, use evidence and logical reasoning.

Claim: "{claim}"

Present your strongest case in 3-4 sentences."""

    def post(self, shared, prep_res, exec_res):
        data = exec_res.model_dump()
        argument = data.get("argument", "").strip()
        key_points = data.get("key_points", [])
        shared["case_for"] = argument
        shared["case_for_points"] = key_points
        print(f"\n🟢 --- Advocate FOR ---")
        print(argument)
        print(f"💡 Key points:")
        for point in key_points:
            print(f"   - {point}")
        print()


class AdvocateAgainst(StructuredNode):
    def __init__(self):
        from utils import get_instructor_client, get_model_name

        super().__init__(
            response_model=AdvocateResponse,
            client=get_instructor_client(),
            model=get_model_name(),
        )

    def prep(self, shared):
        return f"""You are an expert advocate arguing AGAINST this claim. Rebut the opposing argument and present strong counterarguments.

Claim: "{shared["claim"]}"

Your opponent argued:
{shared["case_for"]}

Rebut their points and present your strongest counterarguments in 3-4 sentences."""

    def post(self, shared, prep_res, exec_res):
        data = exec_res.model_dump()
        argument = data.get("argument", "").strip()
        key_points = data.get("key_points", [])
        shared["case_against"] = argument
        shared["case_against_points"] = key_points
        print(f"🔴 --- Advocate AGAINST ---")
        print(argument)
        print(f"💡 Key points:")
        for point in key_points:
            print(f"   - {point}")
        print()


class JudgeDebate(StructuredNode):
    def __init__(self):
        from utils import get_instructor_client, get_model_name

        super().__init__(
            response_model=JudgeResponse,
            client=get_instructor_client(),
            model=get_model_name(),
        )

    def prep(self, shared):
        return f"""You are an impartial judge evaluating a debate.

Claim: "{shared["claim"]}"

Argument FOR:
{shared["case_for"]}

Argument AGAINST:
{shared["case_against"]}

Which argument is stronger? Evaluate the quality of reasoning, evidence, and persuasiveness of each side."""

    def post(self, shared, prep_res, exec_res):
        data = exec_res.model_dump()
        winner = data.get("winner", "Unknown")
        score_for = data.get("score_for", "N/A")
        score_against = data.get("score_against", "N/A")
        verdict = data.get("verdict", "").strip()
        reasoning = data.get("reasoning", "").strip()

        shared["verdict"] = verdict
        shared["winner"] = winner
        shared["score_for"] = score_for
        shared["score_against"] = score_against
        shared["reasoning"] = reasoning

        print(f"⚖️  --- VERDICT ---")
        print(f"🏆 Winner: {winner}")
        print(f"📊 Scores - FOR: {score_for}/10 | AGAINST: {score_against}/10")
        print(f"💬 {verdict}")
        print(f"🔍 {reasoning}")
