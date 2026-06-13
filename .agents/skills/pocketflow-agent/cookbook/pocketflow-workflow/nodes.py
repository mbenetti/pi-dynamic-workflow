import re
from typing import List

from pydantic import BaseModel, Field
from utils.call_llm import call_llm

from pocketflow import BatchNode, Node, StructuredNode


class OutlineSchema(BaseModel):
    sections: List[str] = Field(
        description="List of section titles, at most 3 main sections"
    )


class GenerateOutline(StructuredNode):
    def __init__(self):
        from utils.call_llm import get_instructor_client

        super().__init__(
            response_model=OutlineSchema, client=get_instructor_client(), model="gpt-4o"
        )

    def prep(self, shared):
        return shared["topic"]

    def post(self, shared, prep_res, exec_res):
        # Store the structured data
        outline_dict = exec_res.model_dump()
        shared["outline_yaml"] = outline_dict

        # Extract sections
        sections = outline_dict["sections"]
        shared["sections"] = sections

        # Format for display
        formatted_outline = "\n".join(
            [f"{i + 1}. {section}" for i, section in enumerate(sections)]
        )
        shared["outline"] = formatted_outline

        # Display the results
        print("\n===== OUTLINE (YAML) =====\n")
        print(outline_dict)
        print("\n===== PARSED OUTLINE =====\n")
        print(formatted_outline)
        print("\n=========================\n")

        return "default"


class WriteSimpleContent(BatchNode):
    def prep(self, shared):
        # Get the list of sections to process and store for progress tracking
        self.sections = shared.get("sections", [])
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

        # Show progress for this section
        current_section_index = (
            self.sections.index(section) if section in self.sections else 0
        )
        total_sections = len(self.sections)
        print(
            f"✓ Completed section {current_section_index + 1}/{total_sections}: {section}"
        )

        return section, content

    def post(self, shared, prep_res, exec_res_list):
        # exec_res_list contains [(section, content), (section, content), ...]
        section_contents = {}
        all_sections_content = []

        for section, content in exec_res_list:
            section_contents[section] = content
            all_sections_content.append(f"## {section}\n\n{content}\n")

        draft = "\n".join(all_sections_content)

        # Store the section contents and draft
        shared["section_contents"] = section_contents
        shared["draft"] = draft

        print("\n===== SECTION CONTENTS =====\n")
        for section, content in section_contents.items():
            print(f"--- {section} ---")
            print(content)
            print()
        print("===========================\n")

        return "default"


class ApplyStyle(Node):
    def prep(self, shared):
        """
        Get the draft from shared data
        """
        return shared["draft"]

    def exec(self, draft):
        """
        Apply a specific style to the article
        """
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
        """
        Store the final article in shared data
        """
        shared["final_article"] = exec_res
        print("\n===== FINAL ARTICLE =====\n")
        print(exec_res)
        print("\n========================\n")
        return "default"
