from pydantic import BaseModel, Field
from utils import call_llm, get_instructor_client, search_web

from pocketflow import Node, StructuredNode

TOPICS = [
    "AI agents framework news this week",
    "LLM benchmark results 2025 2026",
    "AI startup funding rounds this month",
]


class StorySchema(BaseModel):
    headline: str = Field(description="Headline of the story")
    summary: str = Field(description="One sentence summary of the story")


class FilterStoriesSchema(BaseModel):
    stories: list[StorySchema] = Field(
        description="List of the 4 most interesting stories"
    )


class BlurbSchema(BaseModel):
    headline: str = Field(description="Headline of the story")
    blurb: str = Field(
        description="Punchy 2-3 sentence newsletter blurb explaining why it matters"
    )


class SummarizeStoriesSchema(BaseModel):
    blurbs: list[BlurbSchema] = Field(
        description="List of newsletter blurbs for each story"
    )


class CurateSources(Node):
    """Searches the web for multiple topics to gather raw stories."""

    def prep(self, shared):
        return shared["topics"]

    def exec(self, topics):
        results = []
        for topic in topics:
            print(f"  🔍 Searching: {topic}")
            results.append(search_web(topic))
        return results

    def post(self, shared, prep_res, exec_res):
        shared["raw_stories"] = exec_res
        print(f"  📚 Curated {len(exec_res)} topic searches")


class FilterStories(StructuredNode):
    """Picks the 4 most interesting stories from raw search results."""

    def __init__(self):
        super().__init__(
            response_model=FilterStoriesSchema,
            client=get_instructor_client(),
            model="gpt-4o",
        )

    def prep(self, shared):
        all_stories = "\n---\n".join(shared["raw_stories"])
        prompt = f"""From these raw search results, pick the 4 most interesting stories.
Score on: novelty, impact on practitioners, concrete details (not hype).

Raw results:
{all_stories}
"""
        return prompt

    def post(self, shared, prep_res, exec_res):
        shared["selected"] = [story.model_dump() for story in exec_res.stories]
        print(f"  💡 Selected {len(shared['selected'])} stories")


class SummarizeStories(StructuredNode):
    """Writes punchy newsletter blurbs for each selected story."""

    def __init__(self):
        super().__init__(
            response_model=SummarizeStoriesSchema,
            client=get_instructor_client(),
            model="gpt-4o",
        )

    def prep(self, shared):
        stories_text = "\n\n".join(
            f"Headline: {s['headline']}\nSummary: {s['summary']}"
            for s in shared["selected"]
        )
        prompt = f"""Write a 2-3 sentence newsletter blurb for each story.
Be punchy, not dry. Include why it matters.

{stories_text}
"""
        return prompt

    def post(self, shared, prep_res, exec_res):
        blurbs = [blurb_entry.model_dump() for blurb_entry in exec_res.blurbs]
        for story, blurb_entry in zip(shared["selected"], blurbs):
            story["blurb"] = blurb_entry["blurb"]
        print(f"  ✍️ Summarized {len(blurbs)} stories")


class FormatNewsletter(Node):
    """Creates a formatted markdown newsletter from the blurbed stories."""

    def prep(self, shared):
        return shared["selected"]

    def exec(self, stories):
        sections = []
        for i, s in enumerate(stories, 1):
            sections.append(f"## {i}. {s['headline']}\n{s['blurb']}")
        body = "\n\n".join(sections)
        return f"# AI Weekly Digest\n\n{body}"

    def post(self, shared, prep_res, exec_res):
        shared["newsletter"] = exec_res
        print("  ✅ Newsletter formatted")
