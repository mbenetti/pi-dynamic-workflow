import sys
from typing import Any, Dict

from pydantic import BaseModel, Field
from utils import call_llm, call_tool, get_instructor_client, get_tools

from pocketflow import Flow, Node, StructuredNode


class ToolDecisionSchema(BaseModel):
    thinking: str = Field(
        description="Step-by-step reasoning about what the question is asking and what numbers to extract"
    )
    tool: str = Field(description="Name of the tool to use")
    reason: str = Field(description="Why you chose this tool")
    parameters: Dict[str, Any] = Field(description="The parameters to pass to the tool")


class GetToolsNode(Node):
    def prep(self, shared):
        """Initialize and get tools"""
        # The question is now passed from main via shared
        print("🔍 Getting available tools...")
        return "simple_server.py"

    def exec(self, server_path):
        """Retrieve tools from the MCP server"""
        tools = get_tools(server_path)
        return tools

    def post(self, shared, prep_res, exec_res):
        """Store tools and process to decision node"""
        tools = exec_res
        shared["tools"] = tools

        # Format tool information for later use
        tool_info = []
        for i, tool in enumerate(tools, 1):
            properties = tool.inputSchema.get("properties", {})
            required = tool.inputSchema.get("required", [])

            params = []
            for param_name, param_info in properties.items():
                param_type = param_info.get("type", "unknown")
                req_status = "(Required)" if param_name in required else "(Optional)"
                params.append(f"    - {param_name} ({param_type}): {req_status}")

            tool_info.append(
                f"[{i}] {tool.name}\n  Description: {tool.description}\n  Parameters:\n"
                + "\n".join(params)
            )

        shared["tool_info"] = "\n".join(tool_info)
        return "decide"


class DecideToolNode(StructuredNode):
    def __init__(self):
        super().__init__(
            response_model=ToolDecisionSchema,
            client=get_instructor_client(),
            model="gpt-4o",
        )

    def prep(self, shared):
        """Prepare the prompt for LLM to process the question"""
        tool_info = shared["tool_info"]
        question = shared["question"]

        prompt = f"""
### CONTEXT
You are an assistant that can use tools via Model Context Protocol (MCP).

### ACTION SPACE
{tool_info}

### TASK
Answer this question: "{question}"

## NEXT ACTION
Analyze the question, extract any numbers or parameters, and decide which tool to use.
"""
        return prompt

    def post(self, shared, prep_res, exec_res):
        """Extract decision from the validated Pydantic model and save to shared context"""
        try:
            decision = exec_res.model_dump()

            shared["tool_name"] = decision["tool"]
            shared["parameters"] = decision["parameters"]
            shared["thinking"] = decision.get("thinking", "")

            print(f"💡 Selected tool: {decision['tool']}")
            print(f"🔢 Extracted parameters: {decision['parameters']}")

            return "execute"
        except Exception as e:
            print(f"❌ Error processing decision: {e}")
            return None


class ExecuteToolNode(Node):
    def prep(self, shared):
        """Prepare tool execution parameters"""
        return shared["tool_name"], shared["parameters"]

    def exec(self, inputs):
        """Execute the chosen tool"""
        tool_name, parameters = inputs
        print(f"🔧 Executing tool '{tool_name}' with parameters: {parameters}")
        result = call_tool("simple_server.py", tool_name, parameters)
        return result

    def post(self, shared, prep_res, exec_res):
        print(f"\n✅ Final Answer: {exec_res}")
        return "done"


if __name__ == "__main__":
    # Default question
    default_question = "What is 982713504867129384651 plus 73916582047365810293746529?"

    # Get question from command line if provided with --
    question = default_question
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            question = arg[2:]
            break

    print(f"🤔 Processing question: {question}")

    # Create nodes
    get_tools_node = GetToolsNode()
    decide_node = DecideToolNode()
    execute_node = ExecuteToolNode()

    # Connect nodes
    get_tools_node - "decide" >> decide_node
    decide_node - "execute" >> execute_node

    # Create and run flow
    flow = Flow(start=get_tools_node)
    shared = {"question": question}
    flow.run(shared)
