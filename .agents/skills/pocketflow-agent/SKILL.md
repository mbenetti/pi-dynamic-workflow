---
name: pocketflow-agent
description: Guidelines, patterns, and examples from the PocketFlow cookbooks to help the Pi agent generate and execute robust multi-step workflows.
---

# PocketFlow Agent Skill

Use this skill when you need to design, generate, or execute dynamic multi-step workflows using the `execute_pocketflow_workflow` tool.

---

## 🏗️ Core Architecture Patterns

PocketFlow workflows are built on three core abstractions:
1. **`Node`**: A single step in the workflow. It has three phases:
   - `prep(shared)`: Extracts and prepares input data from the shared state.
   - `exec(prep_res)`: Performs the actual computation/API call.
   - `post(shared, prep_res, exec_res)`: Updates the shared state and returns an action string (default is `"default"`).
2. **`Flow`**: Orchestrates the execution of nodes. It defines the starting node and maps action strings to successor nodes using the `>>` operator.
3. **`Shared State`**: A dictionary passed between nodes that acts as the single source of truth.

---

## 📐 Step-by-Step Workflow Design Methodology

Before generating any Python code, you MUST follow this structured design process to ensure the workflow is simple, clear, and architecturally sound:

### 1. Requirements Analysis
- Keep it simple and clear.
- If the requirements are abstract or complex, break them down into concrete user stories or scenarios.

### 2. Flow Design & Pattern Selection
- Consider core agentic design patterns and apply them if they fit:
  - **Sequential Workflow**: Simple step-by-step execution.
  - **Map-Reduce**: Split a task into chunks (Map), process them, and merge them into a final result (Reduce).
  - **Agentic Router**: Use an LLM to dynamically find files, select tools, or route to different nodes based on context.
  - **RAG (Retrieval-Augmented Generation)**: Retrieve relevant documents/context before generating a response.
- Write a concise, high-level description of the workflow.
- Create a **Mermaid flowchart** representing the node transitions:
  ```mermaid
  flowchart TD
      firstNode[First Node] --> secondNode[Second Node]
      secondNode --> thirdNode[Third Node]
  ```

### 3. Utility Functions Definition
- Review the available utility functions and include only the necessary ones based on the nodes in the flow.
- Common utilities include:
  - **Call LLM** (`utils/call_llm.py`): For standard text generation.
  - **Get Embedding** (`utils/get_embedding.py`): For vector representations.

### 4. Shared Store Design
- Define the exact structure of the `shared` state dictionary.
- Minimize data redundancy and keep the state clean.
  ```python
  shared = {
      "input_raw_text": "...",
      "processed_chunks": [],
      "final_report": "..."
  }
  ```

### 5. Node Design Specification
- For each node in your flow, carefully specify:
  - **Purpose**: A short explanation of the node's function.
  - **Type**: Regular, Batch, or Async (e.g., `Node`, `BatchNode`, `AsyncNode`).
  - **Steps**:
    - `prep`: What keys/data it reads from the `shared` store.
    - `exec`: What utility function or computation it executes.
    - `post`: What keys/data it writes to the `shared` store, and what action string it returns.

---

## 🌟 Key Cookbook Patterns & Examples

The official [PocketFlow Cookbook Repository](https://github.com/The-Pocket/PocketFlow/tree/main/cookbook) contains dozens of production-ready templates for advanced pipelines (e.g. `RAG`, `Supervisor`, `Majority Vote`, `Multi-Agent Debate`, `Web Crawlers`, and `Self-Healing`).

### 📂 Locally Cached Cookbook Archetypic Blueprints
Because your current skill package has a **fully complete, highly optimized duplicate of the PocketFlow cookbook nested directly inside the skill directory**, you do not need to construct advanced nodes or workflows from scratch! 

If a task matches any of the advanced architectural archetypes below, you should use your `read`, `find`, or `grep` tools to inspect, load, and adapt the fully tested Python scripts located directly inside your active skill installation directory (`{baseDir}/cookbook`):

| Archetype / Use Case | Cookbook Folder Path | Key Components to Audit & Reuse |
| :--- | :--- | :--- |
| **Pristine Structured Outputs** | `{baseDir}/cookbook/pocketflow-structured-output` | Uses `instructor` & `pydantic` to coerce models strictly to JSON schema bounds, stripping reasoning fluff. |
| **Deep Research & Scrapers** | `{baseDir}/cookbook/pocketflow-deep-research` | High-strength sequential queries, downloading links dynamically, local caching, and synthesis. |
| **Self-Healing Diagram Gen** | `{baseDir}/cookbook/pocketflow-self-healing-mermaid` | Automatically intercepts subprocess compile crashes or schemas and feeds traceback error logs into retries. |
| **Parallel Batch Processing** | `{baseDir}/cookbook/pocketflow-parallel-batch` | Leverages `AsyncParallelBatchNode` to parse multiple URLs, PDFs, or files concurrently. |
| **Interactive Human-In-The-Loop** | `{baseDir}/cookbook/pocketflow-cli-hitl` | Temporarily halts flow orchestration to prompt developers over stdin for feedback before continuing. |
| **MCP Tool Servers** | `{baseDir}/cookbook/pocketflow-mcp` | Interlinks Model Context Protocol tools straight into nodes. |
| **Multi-Agent Debates** | `{baseDir}/cookbook/pocketflow-debate` | Runs parallel competitive reasoning nodes before evaluating a consensus decision in a Judge node. |
| **Rag-based Knowledge Graphs** | `{baseDir}/cookbook/pocketflow-agentic-rag` | Connects local vector embeddings and chunks straight into decision trees. |

---

### 1. Structured Output (from [pocketflow-structured-output](https://github.com/The-Pocket/PocketFlow/tree/main/cookbook/pocketflow-structured-output))
Always use `StructuredNode` or `AsyncStructuredNode` when you need guaranteed structured data from an LLM (e.g. OpenAI, Anthropic, or OpenRouter). This integrates the `instructor` library directly into the node structure, returning verified Pydantic model objects that are completely clean of conversational fluff words or markdown wrappers.

```python
from pocketflow import StructuredNode
from pydantic import BaseModel, Field

class ResearchReport(BaseModel):
    summary: str = Field(description="A brief summary of the findings")
    key_points: list[str] = Field(description="Key points extracted from the text")

class ReportNode(StructuredNode):
    def __init__(self, client):
        # Initialize with the response model and instructor client
        super().__init__(response_model=ResearchReport, client=client, model="gpt-4o")

    def prep(self, shared):
        return f"Analyze this text and generate a structured report: {shared['raw_text']}"

    def post(self, shared, prep_res, exec_res):
        # exec_res is guaranteed to be a ResearchReport Pydantic instance
        shared["report"] = exec_res.model_dump()
        return "default"
```

#### 📦 Using Native JSON Schema constraints with Local Ollama
For local models running on **Ollama** (e.g. `lfm2.5:latest`), you can enforce rigid structured JSON outputs by passing a Pydantic model's JSON Schema schema directly to the Ollama endpoint:

```python
import json
import urllib.request
from pocketflow import Node
from pydantic import BaseModel

class KeywordExtract(BaseModel):
    keywords: list[str]

class OllamaStructuredNode(Node):
    def prep(self, shared):
        return shared["text"]

    def exec(self, text):
        prompt = f"Extract keywords from: {text}"
        
        # Pull model_json_schema directly from Pydantic
        schema = KeywordExtract.model_json_schema()
        
        payload = {
            "model": "lfm2.5:latest",
            "prompt": prompt,
            "format": schema,  # Constrains model token-generation directly to JSON schema!
            "stream": False
        }
        
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            payload = json.loads(response.read().decode("utf-8"))
            json_text = payload["response"]
            # Guaranteed to parse cleanly with no conversational intro or markdown code blocks
            parsed = json.loads(json_text)
            return parsed["keywords"]
```

### 2. Parallel Batch Processing (from [pocketflow-parallel-batch](https://github.com/The-Pocket/PocketFlow/tree/main/cookbook/pocketflow-parallel-batch))
When you need to process multiple items concurrently (e.g., scraping multiple URLs, analyzing multiple documents), use `AsyncParallelBatchNode` or `AsyncParallelBatchFlow`.

```python
import asyncio
from pocketflow import AsyncParallelBatchNode

class ParallelScrapeNode(AsyncParallelBatchNode):
    async def prep_async(self, shared):
        # Return a list of items to process in parallel
        return shared["urls"]

    async def exec_async(self, url):
        # This will be executed concurrently for each URL
        html = await fetch_url(url)
        return {"url": url, "html": html}

    async def post_async(self, shared, prep_res, exec_res):
        # exec_res is a list of results in the same order as the input list
        shared["scraped_pages"] = exec_res
        return "default"
```

### 3. Self-Healing, Retries & Fallbacks (from [pocketflow-self-healing-mermaid](https://github.com/The-Pocket/PocketFlow/tree/main/cookbook/pocketflow-self-healing-mermaid))
Nodes have built-in retry and fallback mechanisms. Configure `max_retries` and `wait` on the node class, and override `exec_fallback` if you need custom self-healing.

**Critical Architectural Rules for Isolation:**
* **No `try...except` inside Utilities**: Avoid intercepting or eating errors within your utility methods helpers. Let raw issues propagate to your node's `exec()` phase so PocketFlow can manage retries cleanly.
* **Smart Retry Caching**: In-memory caching can clash with retries by returning the same error. To solve this, pass `self.cur_retry == 0` to your functions to only serve cached results on initial runs, reverting to fresh queries during retries:

```python
from pocketflow import Node

class ResilientScrapeNode(Node):
    def __init__(self):
        # Retry up to 3 times, waiting 2 seconds between attempts
        super().__init__(max_retries=3, wait=2)

    def exec(self, url):
        # Fetch fresh data only if retrying, otherwise leverage cache (if available)
        return fetch_url_with_potential_failure(url, use_cache=(self.cur_retry == 0))

    def exec_fallback(self, prep_res, exc):
        # Called when all retries fail
        print(f"All retries failed for {prep_res}. Falling back to cache.")
        return get_cached_version(prep_res)
```

### 4. Important: Action Strings & Post Phase Routing (CRITICAL)
In PocketFlow, the `post(shared, prep_res, exec_res)` phase MUST update the shared state dictionary and return an action string (e.g., `"default"`, `"success"`, `"failure"`). Do NOT return the shared state dictionary itself!
If you return a dictionary from `post`, it will be passed to successor routing and raise a `TypeError: unhashable type: 'dict'`.

```python
from pocketflow import Node

class ProcessNode(Node):
    def prep(self, shared):
        return shared.get("raw_text")

    def exec(self, raw_text):
        return raw_text.upper()

    def post(self, shared, prep_res, exec_res):
        # 1. Update shared state
        shared["output_text"] = exec_res
        # 2. Return an action string (NOT the shared dictionary!)
        return "default"
```

---

## 📋 Guidelines for Generating Workflows

0. **Workflow File Location Standard (CRITICAL)**:
   - **ALL** nodes, flows, configuration, metadata, and execution scripts for any workflow/project **MUST** reside strictly inside the local folder under `.pi/agents/skills/pocketflow-agent/<name of the project or workflow>`. (Note: folder is spelled `pocketflow-agent` without 'c').
   - All related code, data, outputs, documentation, and info for that specific workflow **MUST** reside entirely inside that folder and in no other place. Do not write or generate files in the workspace root or any other location.
   - **Output Artifacts Exception**: While source files and script definitions must live strictly in the skill's subdirectory, **any generated output files or reports intended for the end-user** should be saved using `os.getcwd()` (e.g., `os.path.join(os.getcwd(), 'report.md')`) so they load automatically inside the actively open workspace directory where the developer or user is currently working.

1. **Imports**:
   - Always import nodes and flows correctly: `from pocketflow import Node, Flow, AsyncNode, AsyncFlow, StructuredNode`.
   - Import LLM utilities from `utils.call_llm`: `from utils.call_llm import call_llm, get_instructor_client`.
2. **Pydantic Schemas**:
   - Always define clear Pydantic schemas for any structured data node.
   - Place Pydantic models at the top of `nodes.py`.
3. **The post Phase and Action String Return**:
   - Make absolute sure that the `post` method in all Nodes returns string action keys (typically `"default"`) and not the `shared` dictionary itself.
4. **Connecting Nodes and Creating Flows (CRITICAL for Tracing and Visualization)**:
   - **Subclass `Flow` or `AsyncFlow` directly** instead of using regular factory functions! The PocketFlow Harness extension uses class matching to dynamically insert the `@trace_flow()` wrapper and generate topology diagrams.
   - Always instantiate a `Flow` or `AsyncFlow` using the parameter name `start`, **never** `start_node` (which will raise a `TypeError: Flow.__init__() got an unexpected keyword argument 'start_node'`).
   - Connect nodes in `flow.py` using the `>>` operator: `node_a >> node_b`.
   - For conditional routing, return custom action strings from `post` and map them:
     ```python
     node_a - "success" >> node_b
     node_a - "failure" >> recovery_node
     ```
   - Basic implementation of a class-based flow:
     ```python
     from pocketflow import Flow
     from nodes import MyNode, NextNode

     # ALWAYS subclass Flow so the extension automatically wraps and traces it!
     class MyCustomFlow(Flow):
         def __init__(self):
             first = MyNode()
             second = NextNode()
             
             # Connect nodes
             first >> second
             
             # CORRECT: Use start=first (DO NOT USE start_node=first!)
             super().__init__(start=first)
     ```
4. **Main Execution**:
   - In `main.py`, define a clear initial state dictionary.
   - Run the class-based flow and print the final state:
     ```python
     from flow import MyCustomFlow
     
     if __name__ == "__main__":
         flow = MyCustomFlow()
         shared = {"input_data": "..."}
         flow.run(shared)
         print(f"Result: {shared}")
     ```

### 5. Running Workflows On-The-Fly with `uv` (Astral)
For instant dependency loading and sandboxed execution without manually creating virtual environments or configuring requirements:
* Declare dependencies using PEP 723 inline script metadata at the top of `main.py`.
* **CRITICAL REQUIREMENT**: The script's inline metadata MUST always contain at least the following basic dependencies:
  ```python
  # /// script
  # requires-python = ">=3.12"
  # dependencies = [
  #     "langfuse>=2.0.0,<3.0.0",
  #     "python-dotenv>=1.0.0",
  #     "pydantic>=2.0.0",
  #     "instructor>=1.0.0",
  # ]
  # ///
  ```
* These basic, core packages are guaranteed to be pre-included and automatically installed by the harness/extension. Any additional, specialized dependencies required for the specialized logic of your target workflow (e.g. `beautifulsoup4`, `httpx`, or target SDKs) should be manually added to the script dependencies list and the tool parameters list.
* **CRITICAL FOR EXTENSION VS. BASH SEPARATION**:
  - **When executing via the `execute_pocketflow_workflow` tool:** Do **NOT** include `"pocketflow"` in the script `dependencies` metadata list! The `pocketflow` core framework and tracing components are dynamically generated and injected by the harness extension upon execution, allowing them to be loaded as a local package directly from the working directory.
  - **When testing your scripts manually in bash (e.g., `uv run main.py`):** Since automatic extension injection is bypassed during manual terminal execution, you should temporarily add `"pocketflow"` to the script `dependencies` list or execute using `uv run --with pocketflow main.py` to ensure standard `uv` downloads and resolves it.
* The harness extension will automatically detect `uv` and run the script inside an isolated sandbox using `uv run main.py`. If you do not provide inline script metadata, the harness dynamically supplies requirements using `--with <deps>` flags.
* You can specify target Python version bounds explicitly on-the-fly (`requires-python = ">=3.12"`). `uv` will automatically download and utilize the desired Python version in isolation if needed!

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "langfuse>=2.0.0,<3.0.0",
#     "python-dotenv>=1.0.0",
#     "pydantic>=2.0.0",
#     "instructor>=1.0.0",
#     "beautifulsoup4",
#     "httpx"
# ]
# ///

from flow import ScanCookbookFlow
...
```

### 6. Decoupled Auto-Tracing with Langfuse (`@trace_flow`)
The dynamic harness automatically handles and injects tracing. If manual class tracing is specified:
* **Never** import tracing via `from pocketflow import trace_flow` (this raises an `ImportError`).
* **Always** import correctly using:
  ```python
  from tracing import trace_flow
  ```
* Ensure `pocketflow` and `tracing` are fully kept decoupled in custom modules.

### 6. Local OCR-Free PDF Parsing with `liteparse`
When processing a large volume of PDFs locally within a Node construct, using `liteparse` (the native in-process Rust PDF compiler) is extremely powerful. Always disable OCR for high-speed pipelines:

```python
import liteparse
from pocketflow import Node

class FastParseNode(Node):
    def exec(self, pdf_path):
        # 1. Initialize LiteParse targeting only page 1 and disabling OCR for sub-second parse times
        parser = liteparse.LiteParse(target_pages="1", ocr_enabled=False)
        result = parser.parse(pdf_path)
        
        # 2. Extract lines or text instantly
        lines = result.text.splitlines()[:10]
        return lines
```

---

## ⚠️ Common Errors and Pitfalls to Avoid

* **`TypeError: Flow.__init__() got an unexpected keyword argument 'start_node'`**:
  * **Cause**: Specifying `start_node=first_node` when initializing a `Flow` or `AsyncFlow`.
  * **Solution**: Always use the parameter name `start`, i.e., `Flow(start=first_node)`.
* **`TypeError: unhashable type: 'dict'`**:
  * **Cause**: Returning the `shared` dictionary from the `post()` or `post_async()` method of a Node.
  * **Solution**: Always return a string action key (e.g., `"default"`) and update the `shared` dictionary in-place.
* **`AttributeError: module 'pocketflow' has no attribute 'AsyncParallelBatchNode'`**:
  * **Cause**: Spelling the parallel batch node or flow names incorrectly.
  * **Solution**: Verify spelling: `AsyncParallelBatchNode`, `AsyncParallelBatchFlow`, `AsyncStructuredNode`.
* **Incorrect Async Execution**:
  * **Cause**: Running an `AsyncFlow` synchronously with `flow.run(shared)`.
  * **Solution**: Always run async flows with `await flow.run_async(shared)` inside an `asyncio.run()` or async loop.
* **Leaked or Broken Virtual Environments on Windows**:
  * **Cause**: Windows terminals inheriting non-functional `VIRTUAL_ENV` pointers.
  * **Solution**: The dynamic harness now fully manages and cleanses the execution process space env automatically. Whenever feasible, let the harness leverage on-the-fly execution with `uv run` to guarantee sandboxing.

