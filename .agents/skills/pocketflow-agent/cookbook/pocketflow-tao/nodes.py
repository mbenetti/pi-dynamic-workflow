# nodes.py

from pydantic import BaseModel, Field
from utils import call_llm

from pocketflow import Node, StructuredNode


class ThinkSchema(BaseModel):
    thinking: str = Field(description="Detailed thinking process")
    action: str = Field(description="Action name, such as 'search' or 'answer'")
    action_input: str = Field(description="Input parameters for the action")
    is_final: bool = Field(
        description="Set to true if this is the final answer, otherwise false"
    )


class ThinkNode(StructuredNode):
    def __init__(self):
        from utils import get_instructor_client

        super().__init__(
            response_model=ThinkSchema, client=get_instructor_client(), model="gpt-4o"
        )

    def prep(self, shared):
        """Prepare the context needed for thinking"""
        query = shared.get("query", "")
        observations = shared.get("observations", [])
        thoughts = shared.get("thoughts", [])
        current_thought_number = shared.get("current_thought_number", 0)

        # Update thought count
        shared["current_thought_number"] = current_thought_number + 1

        # Format previous observations
        observations_text = "\n".join(
            [f"Observation {i + 1}: {obs}" for i, obs in enumerate(observations)]
        )
        if not observations_text:
            observations_text = "No observations yet."

        prompt = f"""
You are an AI assistant solving a problem. Based on the user's query and previous observations, think about what action to take next.

User query: {query}

Previous observations:
{observations_text}

Please think about the next action and decide what to do next.
"""
        return prompt

    def post(self, shared, prep_res, exec_res):
        """Save the thinking result and decide the next step in the flow"""
        thought_data = exec_res.model_dump()
        # Add thought number
        thought_data["thought_number"] = shared.get("current_thought_number", 1)

        # Save thinking result
        if "thoughts" not in shared:
            shared["thoughts"] = []
        shared["thoughts"].append(thought_data)

        # Save action information
        shared["current_action"] = thought_data["action"]
        shared["current_action_input"] = thought_data["action_input"]

        # If it's the final answer, end the flow
        if thought_data.get("is_final", False):
            shared["final_answer"] = thought_data["action_input"]
            print(f"🎯 Final Answer: {thought_data['action_input']}")
            return "end"

        # Otherwise continue with the action
        print(
            f"🤔 Thought {thought_data['thought_number']}: Decided to execute {thought_data['action']}"
        )
        return "action"


class ActionNode(Node):
    def prep(self, shared):
        """Prepare to execute action"""
        action = shared["current_action"]
        action_input = shared["current_action_input"]
        return action, action_input

    def exec(self, inputs):
        """Execute action and return result"""
        action, action_input = inputs

        print(f"🚀 Executing action: {action}, input: {action_input}")

        # Execute different operations based on action type
        if action == "search":
            # Simulate search operation
            result = self.search_web(action_input)
        elif action == "calculate":
            # Simulate calculation operation
            result = self.calculate(action_input)
        elif action == "answer":
            # Direct return answer
            result = action_input
        else:
            # Unknown action type
            result = f"Unknown action type: {action}"

        return result

    def post(self, shared, prep_res, exec_res):
        """Save action result"""
        # Save the current action result
        shared["current_action_result"] = exec_res
        print(f"✅ Action completed, result obtained")

        # Continue to observation node
        return "observe"

    # Simulated tool functions
    def search_web(self, query):
        # This should be actual search logic
        return f"Search results: Information about '{query}'..."

    def calculate(self, expression):
        # This should be actual calculation logic
        try:
            return f"Calculation result: {eval(expression)}"
        except:
            return f"Unable to calculate expression: {expression}"


class ObserveNode(Node):
    def prep(self, shared):
        """Prepare observation data"""
        action = shared["current_action"]
        action_input = shared["current_action_input"]
        action_result = shared["current_action_result"]
        return action, action_input, action_result

    def exec(self, inputs):
        """Analyze action results, generate observation"""
        action, action_input, action_result = inputs

        # Build prompt
        prompt = f"""
        You are an observer, needing to analyze action results and provide objective observations.

        Action: {action}
        Action input: {action_input}
        Action result: {action_result}

        Please provide a concise observation of this result. Don't make decisions, just describe what you see.
        """

        # Call LLM to get observation result
        observation = call_llm(prompt)

        print(f"👁️ Observation: {observation[:50]}...")
        return observation

    def post(self, shared, prep_res, exec_res):
        """Save observation result and decide next flow step"""
        # Save observation result
        if "observations" not in shared:
            shared["observations"] = []
        shared["observations"].append(exec_res)

        # Continue thinking
        return "think"


class EndNode(Node):
    def prep(self, shared):
        """Prepare end node"""

        return {}

    def exec(self, prep_res):
        """Execute end operation"""
        print("Flow ended, thank you for using!")
        return None

    def post(self, shared, prep_res, exec_res):
        """End flow"""
        return None
