from typing import List

from pydantic import BaseModel, Field

from pocketflow import Flow, StructuredNode

# === Define Pydantic Schema for Structured Output ===


class ExperienceItem(BaseModel):
    title: str = Field(description="Job title")
    company: str = Field(description="Company name")


class ResumeSchema(BaseModel):
    name: str = Field(description="Candidate's full name")
    email: str = Field(description="Candidate's email address")
    experience: List[ExperienceItem] = Field(
        description="List of professional experience"
    )
    skill_indexes: List[int] = Field(
        description="List of integers found from the Target Skills list"
    )


# === Define Resume Parser Node using StructuredNode ===


class ResumeParserNode(StructuredNode):
    def __init__(self, max_retries=3, wait=10):
        from utils import get_instructor_client

        super().__init__(
            response_model=ResumeSchema,
            client=get_instructor_client(),
            model="gpt-4o",
            max_retries=max_retries,
            wait=wait,
        )

    def prep(self, shared):
        """Return the prompt for the LLM."""
        resume_text = shared["resume_text"]
        target_skills = shared.get("target_skills", [])
        skill_list_for_prompt = "\n".join(
            [f"{i}: {skill}" for i, skill in enumerate(target_skills)]
        )

        prompt = f"""
Analyze the resume below and extract the requested information.

**Resume:**
```
{resume_text}
```

**Target Skills (use these indexes):**
```
{skill_list_for_prompt}
```
"""
        return prompt

    def post(self, shared, prep_res, exec_res):
        """Store structured data and print it."""
        # exec_res is already a validated ResumeSchema instance!
        # Convert to dict for compatibility with the rest of the flow
        structured_data = exec_res.model_dump()
        shared["structured_data"] = structured_data

        print("\n=== STRUCTURED RESUME DATA (Instructor & Pydantic) ===\n")
        import json

        print(json.dumps(structured_data, indent=2))
        print("\n============================================================\n")
        print("✅ Extracted resume information.")


# === Main Execution Logic ===
if __name__ == "__main__":
    print("=== Resume Parser - Structured Output with Instructor ===\n")

    # --- Configuration ---
    target_skills_to_find = [
        "Team leadership & management",  # 0
        "CRM software",  # 1
        "Project management",  # 2
        "Public speaking",  # 3
        "Microsoft Office",  # 4
        "Python",  # 5
        "Data Analysis",  # 6
    ]
    resume_file = "data.txt"  # Assumes data.txt contains the resume

    # --- Prepare Shared State ---
    shared = {}
    try:
        with open(resume_file, "r") as file:
            shared["resume_text"] = file.read()
    except FileNotFoundError:
        print(f"Error: Resume file '{resume_file}' not found.")
        exit(1)  # Exit if resume file is missing

    shared["target_skills"] = target_skills_to_find

    # --- Define and Run Flow ---
    parser_node = ResumeParserNode(max_retries=3, wait=10)
    flow = Flow(start=parser_node)
    flow.run(shared)  # Execute the parsing node

    # --- Display Found Skills ---
    if "structured_data" in shared and "skill_indexes" in shared["structured_data"]:
        print("\n--- Found Target Skills (from Indexes) ---")
        found_indexes = shared["structured_data"]["skill_indexes"]
        if found_indexes:  # Check if the list is not empty or None
            for index in found_indexes:
                if 0 <= index < len(target_skills_to_find):
                    print(f"- {target_skills_to_find[index]} (Index: {index})")
                else:
                    print(f"- Warning: Found invalid skill index {index}")
        else:
            print("No target skills identified from the list.")
        print("----------------------------------------\n")
