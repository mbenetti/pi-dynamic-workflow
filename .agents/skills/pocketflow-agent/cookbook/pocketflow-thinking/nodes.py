# cookbook/pocketflow-thinking/nodes.py
from __future__ import annotations

import textwrap
from typing import List, Optional

from pydantic import BaseModel, Field
from utils import call_llm

from pocketflow import Node, StructuredNode


class PlanItem(BaseModel):
    description: str = Field(description="Description of the step")
    status: str = Field(
        description="Status of the step (e.g., Pending, Done, Verification Needed)"
    )
    result: Optional[str] = Field(
        default=None, description="Concise summary of the result when Done"
    )
    mark: Optional[str] = Field(
        default=None, description="Reason for Verification Needed or other notes"
    )
    sub_steps: Optional[List[PlanItem]] = Field(
        default=None, description="List of sub-steps breaking down this step"
    )


PlanItem.model_rebuild()


class ThoughtSchema(BaseModel):
    current_thinking: str = Field(
        description="Evaluation of previous thought and thinking for the current step"
    )
    planning: List[PlanItem] = Field(
        description="List of plan items representing the current plan status"
    )
    next_thought_needed: bool = Field(
        description="Set to false ONLY when executing the Conclusion step"
    )


# Helper function to format structured plan for printing
def format_plan(plan_items, indent_level=0):
    indent = "  " * indent_level
    output = []
    if isinstance(plan_items, list):
        for item in plan_items:
            if isinstance(item, dict):
                status = item.get("status", "Unknown")
                desc = item.get("description", "No description")
                result = item.get("result", "")
                mark = item.get("mark", "")  # For verification etc.

                # Format the main step line
                line = f"{indent}- [{status}] {desc}"
                if result:
                    line += f": {result}"
                if mark:
                    line += f" ({mark})"
                output.append(line)

                # Recursively format sub-steps if they exist
                sub_steps = item.get("sub_steps")
                if sub_steps:
                    output.append(format_plan(sub_steps, indent_level + 1))
            elif isinstance(item, str):  # Basic fallback for string items
                output.append(f"{indent}- {item}")
            else:  # Fallback for unexpected types
                output.append(f"{indent}- {str(item)}")

    elif isinstance(plan_items, str):  # Handle case where plan is just an error string
        output.append(f"{indent}{plan_items}")
    else:
        output.append(f"{indent}# Invalid plan format: {type(plan_items)}")

    return "\n".join(output)


# Helper function to format structured plan for the prompt (simplified view)
def format_plan_for_prompt(plan_items, indent_level=0):
    indent = "  " * indent_level
    output = []
    # Simplified formatting for prompt clarity
    if isinstance(plan_items, list):
        for item in plan_items:
            if isinstance(item, dict):
                status = item.get("status", "Unknown")
                desc = item.get("description", "No description")
                line = f"{indent}- [{status}] {desc}"
                output.append(line)
                sub_steps = item.get("sub_steps")
                if sub_steps:
                    # Indicate nesting without full recursive display in prompt
                    output.append(format_plan_for_prompt(sub_steps, indent_level + 1))
            else:  # Fallback
                output.append(f"{indent}- {str(item)}")
    else:
        output.append(f"{indent}{str(plan_items)}")
    return "\n".join(output)


class ChainOfThoughtNode(StructuredNode):
    def __init__(self):
        from utils import get_instructor_client

        super().__init__(
            response_model=ThoughtSchema,
            client=get_instructor_client(),
            model="claude-3-7-sonnet-20250219",
        )

    def prep(self, shared):
        problem = shared.get("problem", "")
        thoughts = shared.get("thoughts", [])
        current_thought_number = shared.get("current_thought_number", 0)

        shared["current_thought_number"] = current_thought_number + 1

        # Format previous thoughts and extract last plan structure
        thoughts_text = ""
        last_plan_structure = None  # Will store the list of dicts
        if thoughts:
            thoughts_text_list = []
            for i, t in enumerate(thoughts):
                thought_block = f"Thought {t.get('thought_number', i + 1)}:\n"
                thinking = textwrap.dedent(t.get("current_thinking", "N/A")).strip()
                thought_block += f"  Thinking:\n{textwrap.indent(thinking, '    ')}\n"

                plan_list = t.get("planning", [])
                # Use the recursive helper for display formatting
                plan_str_formatted = format_plan(plan_list, indent_level=2)
                thought_block += f"  Plan Status After Thought {t.get('thought_number', i + 1)}:\n{plan_str_formatted}"

                if i == len(thoughts) - 1:
                    last_plan_structure = plan_list  # Keep the actual structure

                thoughts_text_list.append(thought_block)

            thoughts_text = "\n--------------------\n".join(thoughts_text_list)
        else:
            thoughts_text = "No previous thoughts yet."
            # Suggest an initial plan structure using dictionaries
            last_plan_structure = [
                {"description": "Understand the problem", "status": "Pending"},
                {"description": "Develop a high-level plan", "status": "Pending"},
                {"description": "Conclusion", "status": "Pending"},
            ]

        # Format the last plan structure for the prompt context using the specific helper
        last_plan_text_for_prompt = (
            format_plan_for_prompt(last_plan_structure)
            if last_plan_structure
            else "# No previous plan available."
        )

        # --- Construct Prompt ---
        instruction_base = textwrap.dedent(f"""
            Your task is to generate the next thought (Thought {current_thought_number + 1}).

            Instructions:
            1.  **Evaluate Previous Thought:** If not the first thought, start `current_thinking` by evaluating Thought {current_thought_number}. State: "Evaluation of Thought {current_thought_number}: [Correct/Minor Issues/Major Error - explain]". Address errors first.
            2.  **Execute Step:** Execute the first step in the plan with `status: Pending`.
            3.  **Maintain Plan (Structure):** Generate an updated `planning` list. Each item should be a dictionary with keys: `description` (string), `status` (string: "Pending", "Done", "Verification Needed"), and optionally `result` (string, concise summary when Done) or `mark` (string, reason for Verification Needed). Sub-steps are represented by a `sub_steps` key containing a *list* of these dictionaries.
            4.  **Update Current Step Status:** In the updated plan, change the `status` of the executed step to "Done" and add a `result` key with a concise summary. If verification is needed based on evaluation, change status to "Verification Needed" and add a `mark`.
            5.  **Refine Plan (Sub-steps):** If a "Pending" step is complex, add a `sub_steps` key to its dictionary containing a list of new step dictionaries (status: "Pending") breaking it down. Keep the parent step's status "Pending" until all sub-steps are "Done".
            6.  **Refine Plan (Errors):** Modify the plan logically based on evaluation findings (e.g., change status, add correction steps).
            7.  **Final Step:** Ensure the plan progresses towards a final step dictionary like `{{'description': "Conclusion", 'status': "Pending"}}`.
            8.  **Termination:** Set `next_thought_needed` to `false` ONLY when executing the step with `description: "Conclusion"`.
        """)

        if not thoughts:
            instruction_context = textwrap.dedent("""
                **This is the first thought:** Create an initial plan as a list of dictionaries (keys: description, status). Include sub-steps via the `sub_steps` key if needed. Then, execute the first step in `current_thinking` and provide the updated plan (marking step 1 `status: Done` with a `result`).
            """)
        else:
            instruction_context = textwrap.dedent(f"""
                **Previous Plan (Simplified View):**
                {last_plan_text_for_prompt}

                Start `current_thinking` by evaluating Thought {current_thought_number}. Then, proceed with the first step where `status: Pending`. Update the plan structure (list of dictionaries) reflecting evaluation, execution, and refinements.
            """)

        prompt = textwrap.dedent(f"""
            You are a meticulous AI assistant solving a complex problem step-by-step using a structured plan. You critically evaluate previous steps, refine the plan with sub-steps if needed, and handle errors logically. Use the specified YAML dictionary structure for the plan.

            Problem: {problem}

            Previous thoughts:
            {thoughts_text}
            --------------------
            {instruction_base}
            {instruction_context}
        """)

        return prompt

    def post(self, shared, prep_res, exec_res):
        thought_data = exec_res.model_dump()
        thought_data["thought_number"] = shared.get("current_thought_number", 1)

        # Add the new thought to the list
        if "thoughts" not in shared:
            shared["thoughts"] = []
        shared["thoughts"].append(thought_data)

        # Extract plan for printing using the updated recursive helper function
        plan_list = thought_data.get("planning", ["Error: Planning data missing."])
        plan_str_formatted = format_plan(plan_list, indent_level=1)

        thought_num = thought_data.get("thought_number", "N/A")
        current_thinking = thought_data.get(
            "current_thinking", "Error: Missing thinking content."
        )
        dedented_thinking = textwrap.dedent(current_thinking).strip()

        # Primary termination signal
        if not thought_data.get("next_thought_needed", True):
            shared["solution"] = (
                dedented_thinking  # Solution is the thinking content of the final step
            )
            print(f"\nThought {thought_num} (Conclusion):")
            print(f"{textwrap.indent(dedented_thinking, '  ')}")
            print("\nFinal Plan Status:")
            print(textwrap.indent(plan_str_formatted, "  "))
            print("\n=== FINAL SOLUTION ===")
            print(dedented_thinking)
            print("======================\n")
            return "end"

        # Otherwise, continue the chain
        print(f"\nThought {thought_num}:")
        print(f"{textwrap.indent(dedented_thinking, '  ')}")
        print("\nCurrent Plan Status:")
        print(textwrap.indent(plan_str_formatted, "  "))
        print("-" * 50)

        return "continue"
