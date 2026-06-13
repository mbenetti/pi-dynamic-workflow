from pydantic import BaseModel, Field
from utils import call_llm

from pocketflow import Flow, Node, StructuredNode


class GuardrailSchema(BaseModel):
    valid: bool = Field(
        description="Whether the user query is related to travel and is safe/appropriate"
    )
    reason: str = Field(description="Explanation of why the query is valid or invalid")


class UserInputNode(Node):
    def prep(self, shared):
        # Initialize messages if this is the first run
        if "messages" not in shared:
            shared["messages"] = []
            print(
                "Welcome to the Travel Advisor Chat! Type 'exit' to end the conversation."
            )

        return None

    def exec(self, _):
        # Get user input
        user_input = input("\nYou: ")
        return user_input

    def post(self, shared, prep_res, exec_res):
        user_input = exec_res

        # Check if user wants to exit
        if user_input and user_input.lower() == "exit":
            print("\nGoodbye! Safe travels!")
            return None  # End the conversation

        # Store user input in shared
        shared["user_input"] = user_input

        # Move to guardrail validation
        return "validate"


class GuardrailNode(StructuredNode):
    def __init__(self):
        from utils import get_instructor_client

        super().__init__(
            response_model=GuardrailSchema,
            client=get_instructor_client(),
            model="gpt-4o",
        )

    def prep(self, shared):
        # Get the user input from shared data
        user_input = shared.get("user_input", "")

        # Basic validation checks
        if not user_input or user_input.strip() == "":
            return {
                "error": "Your query is empty. Please provide a travel-related question."
            }

        if len(user_input.strip()) < 3:
            return {
                "error": "Your query is too short. Please provide more details about your travel question."
            }

        # LLM-based validation for travel topics
        prompt = f"""
Evaluate if the following user query is related to travel advice, destinations, planning, or other travel topics.
The chat should ONLY answer travel-related questions and reject any off-topic, harmful, or inappropriate queries.
User query: {user_input}
"""
        return prompt

    def exec(self, prep_res):
        # If prep returned a basic validation error, bypass the LLM call
        if isinstance(prep_res, dict) and "error" in prep_res:
            return GuardrailSchema(valid=False, reason=prep_res["error"])

        # Otherwise, let StructuredNode handle the LLM call
        return super().exec(prep_res)

    def post(self, shared, prep_res, exec_res):
        # exec_res is a validated GuardrailSchema instance
        is_valid = exec_res.valid
        message = exec_res.reason

        if not is_valid:
            # Display error message to user
            print(f"\nTravel Advisor: {message}")
            # Skip LLM call and go back to user input
            return "retry"

        # Valid input, add to message history
        shared["messages"].append({"role": "user", "content": shared["user_input"]})
        # Proceed to LLM processing
        return "process"


class LLMNode(Node):
    def prep(self, shared):
        # Add system message if not present
        if not any(msg.get("role") == "system" for msg in shared["messages"]):
            shared["messages"].insert(
                0,
                {
                    "role": "system",
                    "content": "You are a helpful travel advisor that provides information about destinations, travel planning, accommodations, transportation, activities, and other travel-related topics. Only respond to travel-related queries and keep responses informative and friendly. Your response are concise in 100 words.",
                },
            )

        # Return all messages for the LLM
        return shared["messages"]

    def exec(self, messages):
        # Call LLM with the entire conversation history
        response = call_llm(messages)
        return response

    def post(self, shared, prep_res, exec_res):
        # Print the assistant's response
        print(f"\nTravel Advisor: {exec_res}")

        # Add assistant message to history
        shared["messages"].append({"role": "assistant", "content": exec_res})

        # Loop back to continue the conversation
        return "continue"


# Create the flow with nodes and connections
user_input_node = UserInputNode()
guardrail_node = GuardrailNode()
llm_node = LLMNode()

# Create flow connections
user_input_node - "validate" >> guardrail_node
guardrail_node - "retry" >> user_input_node  # Loop back if input is invalid
guardrail_node - "process" >> llm_node
llm_node - "continue" >> user_input_node  # Continue conversation

flow = Flow(start=user_input_node)

# Start the chat
if __name__ == "__main__":
    shared = {}
    flow.run(shared)
