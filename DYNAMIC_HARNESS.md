# 🚀 PocketFlow Dynamic Harness Extension Guide

The **PocketFlow Dynamic Harness** is a Pi extension that enables on-the-fly generation, installation, tracing, execution, and self-healing of custom PocketFlow graphs. 

This document serves as the developer and user reference manual on how the harness works, its dependencies, installation manual, and instructions for sharing.

---

## 🏗️ Requirements & System Dependencies

Before installing, make sure your host machine satisfies the following runtime dependencies:

1. **`uv` (Highly Recommended)**: The harness is highly optimized to run with **Astral `uv`** (a fast Python package manager) for instant execution. When `uv` is present on your terminal `$PATH`, the harness executes workflows on-the-fly in isolated virtual environments with automated dependency resolution, skipping manual `pip` installs entirely.
   - **Installation**:
     ```bash
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```
2. **`Python 3.10+`**: Python must be installed locally on the host machine.
3. **`git`**: Integrated workspace checking and cloning dependencies.

---

## 🛠️ Custom Tool API

The harness registers a custom tool `execute_pocketflow_workflow` which triggers the dynamic setup, dependency resolution, auto-tracing generation, and python execution of your graphs.

### Inputs for `execute_pocketflow_workflow`

* **`task_name`**: A short slug (e.g., `pricing_comparison`) used to create a sandbox folder at `.pi/pocketflow/<task_name>`.
* **`nodes_code`**: The complete script for `nodes.py` defining your `Node` class.
* **`flow_code`**: The complete script for `flow.py` orchestrating your graph.
* **`main_code`**: The complete script for `main.py` initiating the dictionary state and calling `flow.run()`.
* **`requirements`**: List of pip requirements needed specifically for your custom logic (e.g. `['beautifulsoup4', 'numpy']`). (Core libraries like `pocketflow`, `instructor`, `pydantic`, `python-dotenv`, and `langfuse` are installed automatically).

---

## 🏁 Architectural Patterns & Usability Guidelines

To make generating dynamic workflows easier and less error-prone, keep the following hard rules in mind:

### 1. ⚠️ Crucial Node Routing: Always Return Action Strings
A common mistake when manually drafting nodes is having the `post()` method return the `shared` state dictionary:
```python
# ❌ INCORRECT (Raises TypeError: unhashable type: 'dict')
def post(self, shared, prep_res, exec_res):
    shared["result"] = exec_res
    return shared  # NO!
```
The `post` method's workflow responsibility is to update `shared` **in-place** and return a string corresponding to the action key indicating the next transition edge:
```python
#  CORRECT
def post(self, shared, prep_res, exec_res):
    shared["result"] = exec_res
    return "default"  # YES!
```

### 2. ⚡ Direct LLM Integration
You do not need to initialize your own client or worry about picking the right api tokens. The extension automatically generates a unified `utils/call_llm.py` library synced with the active LLM of your current Pi workspace session.

In your nodes, import these functions directly:
```python
from utils.call_llm import call_llm, get_instructor_client
```
* Use `call_llm(prompt)` for standard quick text generation.
* Use `get_instructor_client()` with a Pydantic Model for rigid structure extraction nodes:
  ```python
  client = get_instructor_client()
  extracted = client.chat.completions.create(
      model="...", # Your nodes can optionally read this dynamically or pass defaults Since standard providers are mapped!
      response_model=MyModel,
      messages=[{"role": "user", "content": prompt}]
  )
  ```

### 3. 🔍 Auto Trace Tracing with Langfuse (Flow Subclassing Requirement)
If Langfuse credentials (`LANGFUSE_SECRET_KEY` and `LANGFUSE_PUBLIC_KEY`) are present in your process environment or your project's `.env`, the harness **automatically** injects a tracing module and wraps your workflows using `@trace_flow()`. 

No manual instrumentation of code is necessary. However, a **critical design rule** applies:

⚠️ **Your workflow class in `flow.py` MUST subclass `Flow` or `AsyncFlow` directly**, rather than defining a generic constructor function:

```python
# ❌ INCORRECT (Harness tracing regex will NOT find this and tracing will fail)
def create_flow():
    node_a = MyNode()
    return Flow(start=node_a)

# ✅ CORRECT (Standard subclassing allows @trace_flow() wrapping!)
class MyEpicJourneyFlow(Flow):
    def __init__(self):
        node_a = MyNode()
        super().__init__(start=node_a)
```

You will see active flow and step tracing output in stdout and inside your Langfuse dashboard showing full performance breakdowns of your runs when following this pattern.

---

## 📦 How to Install the Extension in another Pi Environment

To install, load, and activate the PocketFlow Harness extension in a brand new Pi environment, follow these steps:

### Option A: Local Workspace Scope (Recommended for specific folders)
1. Within your project repository, create an folder structure:
   ```bash
   mkdir -p .pi/extensions
   ```
2. Copy the extension file `pocketflow-harness.ts` into `.pi/extensions/`.
3. In your main terminal interface, start Pi or reload with:
   ```bash
   pi
   ```
   If prompted to "Trust project?" select **yes** to let project-local TypeScript extensions execute.

### Option B: User Global Scope (Make available across ALL directories)
1. Create your user global Pi extension folder:
   ```bash
   mkdir -p ~/.pi/agent/extensions
   ```
2. Copy the `pocketflow-harness.ts` file right in:
   ```bash
   cp pocketflow-harness.ts ~/.pi/agent/extensions/
   ```
3. Boot up `pi` from any terminal directory. The harness will automatically register globally and be active on startup.

---

## 🌐 Publish as a Shared GitHub Repo Package
If you plan to publish this extension on GitHub, you can structure it as a standalone distributable Pi Package.

### File Structure
```
my-pocketflow-harness-pack/
├── package.json
├── README.md
└── src/
    └── index.ts (The pocketflow-harness.ts source code)
```

### `package.json` Package Manifesto
```json
{
  "name": "pi-pocketflow-harness",
  "version": "1.0.0",
  "description": "Dynamic on-the-fly execution, tracing, and visualization of PocketFlow workflows inside Pi agent.",
  "dependencies": {},
  "pi": {
    "extensions": ["./src/index.ts"]
  }
}
```

### Installation from CLI via Shareable Link
Once compiled and pushed to GitHub under your user profile, other people can install your package globally with a single command line call:
```bash
pi install git:github.com/your-username/pi-pocketflow-harness
```
This is fully auto-discovered, cloned dynamically under `~/.pi/agent/git/`, and registered on startup!
