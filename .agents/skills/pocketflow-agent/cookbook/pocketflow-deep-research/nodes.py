from typing import Literal, Optional

from pydantic import BaseModel, Field
from utils import call_llm, search_web

from pocketflow import BatchNode, Node, StructuredNode


class PlannerResponse(BaseModel):
    queries: list[str] = Field(
        description="List of 3 diverse search queries to research the topic."
    )


class SynthesizerResponse(BaseModel):
    action: Literal["research", "finalize"] = Field(
        description="Choose 'research' if more information is needed, or 'finalize' if the information is sufficient."
    )
    feedback: Optional[str] = Field(
        None,
        description="What's missing to write a comprehensive report. Required if action is 'research'.",
    )
    content: Optional[str] = Field(
        None,
        description="The final research report in markdown. Required if action is 'finalize'.",
    )


class PlannerNode(StructuredNode):
    """Generates diverse search queries to research a topic."""

    def __init__(self):
        from utils import get_instructor_client, get_model_name

        super().__init__(
            response_model=PlannerResponse,
            client=get_instructor_client(),
            model=get_model_name(),
        )

    def prep(self, shared):
        topic = shared["topic"]
        feedback = shared.get("feedback", "")

        if not feedback:
            instruction = f"Generate 3 diverse search queries to research: '{topic}'."
        else:
            instruction = (
                f"We are researching '{topic}'.\n"
                f"Gaps to fill: {feedback}\n\n"
                f"Generate 3 search queries to fill these gaps."
            )
        return instruction

    def post(self, shared, prep_res, exec_res):
        data = exec_res.model_dump()
        queries = data.get("queries", [])
        shared["current_queries"] = queries
        print(f"  🔍 Planner: {queries}")


class ResearcherNode(BatchNode):
    """Searches the web for each query and extracts key facts."""

    def prep(self, shared):
        return shared["current_queries"]

    def exec(self, query):
        print(f"  🌐 Searching: {query}")
        raw = search_web(query)
        extracted = call_llm(
            f"Extract key facts relevant to this query. Be brief.\n\n"
            f"Query: {query}\n"
            f"Search result:\n{raw}"
        )
        return f"Q: {query}\nFacts: {extracted}"

    def post(self, shared, prep_res, exec_res):
        if "notes" not in shared:
            shared["notes"] = []
        shared["notes"].extend(exec_res)
        print(f"  📚 Researcher: collected {len(exec_res)} sets of notes")


class SynthesizerNode(StructuredNode):
    """Checks if enough info is gathered; loops back or generates final report."""

    def __init__(self):
        from utils import get_instructor_client, get_model_name

        super().__init__(
            response_model=SynthesizerResponse,
            client=get_instructor_client(),
            model=get_model_name(),
        )

    def prep(self, shared):
        topic = shared["topic"]
        notes = shared.get("notes", [])
        loops = shared.get("loop_count", 0)

        # Force finalization after 2 research loops
        if loops >= 2:
            notes_text = "\n---\n".join(notes)
            return f"""We are researching: "{topic}"

Notes collected:
{notes_text}

You MUST finalize the research now. Write a concise research report in markdown. Set action to 'finalize' and provide the report in the 'content' field."""

        notes_text = "\n---\n".join(notes)
        return f"""We are researching: "{topic}"

Notes collected:
{notes_text}

Is the information sufficient for a comprehensive report? Choose 'research' if more information is needed (and provide feedback on what's missing), or 'finalize' if the information is sufficient (and provide the final report in markdown)."""

    def post(self, shared, prep_res, exec_res):
        data = exec_res.model_dump()
        if data["action"] == "research":
            shared["loop_count"] = shared.get("loop_count", 0) + 1
            shared["feedback"] = data.get("feedback", "") or ""
            print(f"  🤔 Synthesizer: gaps found — {shared['feedback']}")
            return "research"

        shared["report"] = data.get("content", "") or ""
        print("  ✅ Synthesizer: report complete")
        return "finalize"
