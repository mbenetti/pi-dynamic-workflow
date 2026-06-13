from pydantic import BaseModel, Field
from utils.call_llm import call_llm

from pocketflow import BatchNode, Node, StructuredNode


class OutlineResponse(BaseModel):
    sections: list[str] = Field(
        description="List of at most 3 main section titles for the article."
    )


class GenerateOutline(StructuredNode):
    def __init__(self):
        from utils.call_llm import get_instructor_client

        super().__init__(
            response_model=OutlineResponse,
            client=get_instructor_client(),
            model="gpt-4o",
        )

    def prep(self, shared):
        return f"Create a simple outline for an article about {shared['topic']}. Include at most 3 main sections (no subsections)."

    def post(self, shared, prep_res, exec_res):
        data = exec_res.model_dump()
        sections = data.get("sections", [])
        shared["sections"] = sections

        # Send progress update via SSE queue
        progress_msg = {
            "step": "outline",
            "progress": 33,
            "data": {"sections": sections},
        }
        shared["sse_queue"].put_nowait(progress_msg)

        return "default"


class WriteContent(BatchNode):
    def prep(self, shared):
        # Store sections and sse_queue for use in exec
        self.sections = shared.get("sections", [])
        self.sse_queue = shared["sse_queue"]
        return self.sections

    def exec(self, section):
        prompt = f"""
Write a short paragraph (MAXIMUM 100 WORDS) about this section:

{section}

Requirements:
- Explain the idea in simple, easy-to-understand terms
- Use everyday language, avoiding jargon
- Keep it very concise (no more than 100 words)
- Include one brief example or analogy
"""
        content = call_llm(prompt)

        # Send progress update for this section
        current_section_index = (
            self.sections.index(section) if section in self.sections else 0
        )
        total_sections = len(self.sections)

        # Progress from 33% (after outline) to 66% (before styling)
        # Each section contributes (66-33)/total_sections = 33/total_sections percent
        section_progress = 33 + ((current_section_index + 1) * 33 // total_sections)

        progress_msg = {
            "step": "content",
            "progress": section_progress,
            "data": {
                "section": section,
                "completed_sections": current_section_index + 1,
                "total_sections": total_sections,
            },
        }
        self.sse_queue.put_nowait(progress_msg)

        return f"## {section}\n\n{content}\n"

    def post(self, shared, prep_res, exec_res_list):
        draft = "\n".join(exec_res_list)
        shared["draft"] = draft
        return "default"


class ApplyStyle(Node):
    def prep(self, shared):
        return shared["draft"]

    def exec(self, draft):
        prompt = f"""
Rewrite the following draft in a conversational, engaging style:

{draft}

Make it:
- Conversational and warm in tone
- Include rhetorical questions that engage the reader
- Add analogies and metaphors where appropriate
- Include a strong opening and conclusion
"""
        return call_llm(prompt)

    def post(self, shared, prep_res, exec_res):
        shared["final_article"] = exec_res

        # Send completion update via SSE queue
        progress_msg = {
            "step": "complete",
            "progress": 100,
            "data": {"final_article": exec_res},
        }
        shared["sse_queue"].put_nowait(progress_msg)

        return "default"
