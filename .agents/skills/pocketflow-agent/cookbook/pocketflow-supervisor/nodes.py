import random
from typing import Literal, Optional

from pydantic import BaseModel, Field
from utils import call_llm, search_web

from pocketflow import Node, StructuredNode


class DecideActionSchema(BaseModel):
    thinking: str = Field(description="Your step-by-step reasoning process")
    action: Literal["search", "answer"] = Field(
        description="The action to take: search or answer"
    )
    reason: str = Field(description="Why you chose this action")
    search_query: Optional[str] = Field(
        default="", description="Specific search query if action is search"
    )


class DecideAction(StructuredNode):
    def __init__(self):
        from utils import get_instructor_client

        super().__init__(
            response_model=DecideActionSchema,
            client=get_instructor_client(),
            model="gpt-4o",
        )

    def prep(self, shared):
        """Prepare the context and question for the decision-making process."""
        # Get the current context (default to "No previous search" if none exists)
        context = shared.get("context", "No previous search")
        # Get the question from the shared store
        question = shared["question"]

        print(f"🤔 Agent deciding what to do next...")

        # Create a prompt to help the LLM decide what to do next
        prompt = f"""
### CONTEXT
You are a research assistant that can search the web.
Question: {question}
Previous Research: {context}

### ACTION SPACE
[1] search
  Description: Look up more information on the web
  Parameters:
    - query (str): What to search for

[2] answer
  Description: Answer the question with current knowledge
  Parameters:
    - answer (str): Final answer to the question

## NEXT ACTION
Decide the next action based on the context and available actions.
"""
        return prompt

    def post(self, shared, prep_res, exec_res):
        """Save the decision and determine the next step in the flow."""
        decision = exec_res.model_dump()
        # If LLM decided to search, save the search query
        if decision["action"] == "search":
            shared["search_query"] = decision["search_query"]
            print(f"🔍 Agent decided to search for: {decision['search_query']}")
        else:
            print(f"💡 Agent decided to answer the question")

        # Return the action to determine the next node in the flow
        return decision["action"]


class SearchWeb(Node):
    def prep(self, shared):
        """Get the search query from the shared store."""
        return shared["search_query"]

    def exec(self, search_query):
        """Search the web for the given query."""
        # Call the search utility function
        print(f"🌐 Searching the web for: {search_query}")
        results = search_web(search_query)
        return results

    def post(self, shared, prep_res, exec_res):
        """Save the search results and go back to the decision node."""
        # Add the search results to the context in the shared store
        previous = shared.get("context", "")
        shared["context"] = (
            previous
            + "\n\nSEARCH: "
            + shared["search_query"]
            + "\nRESULTS: "
            + exec_res
        )

        print(f"📚 Found information, analyzing results...")

        # Always go back to the decision node after searching
        return "decide"


class UnreliableAnswerNode(Node):
    def prep(self, shared):
        """Get the question and context for answering."""
        return shared["question"], shared.get("context", "")

    def exec(self, inputs):
        """Call the LLM to generate a final answer with 50% chance of returning a dummy answer."""
        question, context = inputs

        # 50% chance to return a dummy answer
        if random.random() < 0.5:
            print(f"🤪 Generating unreliable dummy answer...")
            return "Sorry, I'm on a coffee break right now. All information I provide is completely made up anyway. The answer to your question is 42, or maybe purple unicorns. Who knows? Certainly not me!"

        print(f"✍️ Crafting final answer...")

        # Create a prompt for the LLM to answer the question
        prompt = f"""
### CONTEXT
Based on the following information, answer the question.
Question: {question}
Research: {context}

## YOUR ANSWER:
Provide a comprehensive answer using the research results.
"""
        # Call the LLM to generate an answer
        answer = call_llm(prompt)
        return answer

    def post(self, shared, prep_res, exec_res):
        """Save the final answer and complete the flow."""
        # Save the answer in the shared store
        shared["answer"] = exec_res

        print(f"✅ Answer generated successfully")


class SupervisorNode(Node):
    def prep(self, shared):
        """Get the current answer for evaluation."""
        return shared["answer"]

    def exec(self, answer):
        """Check if the answer is valid or nonsensical."""
        print(f"    🔍 Supervisor checking answer quality...")

        # Check for obvious markers of the nonsense answers
        nonsense_markers = [
            "coffee break",
            "purple unicorns",
            "made up",
            "42",
            "Who knows?",
        ]

        # Check if the answer contains any nonsense markers
        is_nonsense = any(marker in answer for marker in nonsense_markers)

        if is_nonsense:
            return {
                "valid": False,
                "reason": "Answer appears to be nonsensical or unhelpful",
            }
        else:
            return {"valid": True, "reason": "Answer appears to be legitimate"}

    def post(self, shared, prep_res, exec_res):
        """Decide whether to accept the answer or restart the process."""
        if exec_res["valid"]:
            print(f"    ✅ Supervisor approved answer: {exec_res['reason']}")
        else:
            print(f"    ❌ Supervisor rejected answer: {exec_res['reason']}")
            # Clean up the bad answer
            shared["answer"] = None
            # Add a note about the rejected answer
            context = shared.get("context", "")
            shared["context"] = (
                context
                + "\n\nNOTE: Previous answer attempt was rejected by supervisor."
            )
            return "retry"
