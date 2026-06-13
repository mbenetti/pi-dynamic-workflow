from typing import Literal, Optional

from pydantic import BaseModel, Field
from utils import call_llm, get_instructor_client, search_web_duckduckgo

from pocketflow import Node, StructuredNode


class DecisionSchema(BaseModel):
    thinking: str = Field(description="Step-by-step reasoning process")
    action: Literal["search", "answer"] = Field(description="The action to take next")
    reason: str = Field(description="Why you chose this action")
    answer: Optional[str] = Field(
        default=None, description="Final answer to the question, if action is answer"
    )
    search_query: Optional[str] = Field(
        default=None, description="Specific search query, if action is search"
    )


class DecideAction(StructuredNode):
    def __init__(self):
        super().__init__(
            response_model=DecisionSchema,
            client=get_instructor_client(),
            model="gpt-4o",
        )

    def prep(self, shared):
        """Prepare the context and question for the decision-making process."""
        # Get the current context (default to "No previous search" if none exists)
        context = shared.get("context", "No previous search")
        # Get the question from the shared store
        question = shared["question"]

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
        # Dump the model to a dictionary
        decision = exec_res.model_dump()

        # If LLM decided to search, save the search query
        if decision["action"] == "search":
            shared["search_query"] = decision["search_query"]
            print(f"🔍 Agent decided to search for: {decision['search_query']}")
        else:
            shared["context"] = decision[
                "answer"
            ]  # save the context if LLM gives the answer without searching.
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
        results = search_web_duckduckgo(search_query)
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


class AnswerQuestion(Node):
    def prep(self, shared):
        """Get the question and context for answering."""
        return shared["question"], shared.get("context", "")

    def exec(self, inputs):
        """Call the LLM to generate a final answer."""
        question, context = inputs

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

        # We're done - no need to continue the flow
        return "done"
