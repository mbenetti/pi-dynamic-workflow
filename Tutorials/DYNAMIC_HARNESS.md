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

To make generating dynamic workflows easier and less error-prone, keep the following design choices and guidelines in mind:

### ⚙️ Core Architecture Design Details

The PocketFlow Dynamic Harness runs as a fully sandboxed, highly-isolated local compiler designed for zero-config workflows. The internal pipeline functions around three core structural choices:

#### 1. Embedded Bundles (Engine Autonomy)
Rather than requesting users or environments to download framework dependencies via PyPI or NPM, the extension **dynamically writes the core codebases** directly into the task workspace. 
* **Core Engine**: A 200-line complete replication of the PocketFlow framework (`pocketflow/`) is written into `.pi/pocketflow/<task_name>/pocketflow/`.
* **Tracing Module**: A modular, optimized version of the Langfuse tracing package (`tracing/`) is compiled inside `.pi/pocketflow/<task_name>/tracing/`.
This absolute separation makes workspaces 100% self-contained/local, removes download lag, and guarantees complete immunity from framework version conflicts.

#### 2. Automatic Parent Process Propagation (.env Propagation)
The dynamic harness bypasses manual `.env` file reading and path resolution inside your scripts. When executing subprocesses (via `uv run` or local `python`), Node's parent `process.env` is automatically mapped and propagated:
* Global or local shell environment variables are forwarded automatically.
* Workspace variables configured inside your active `pi` `.env` block are loaded on-the-fly and parsed.
* System configurations, such as your chosen `LANGFUSE_PUBLIC_KEY`, API tokens, and model overrides (`OPENROUTER_API_KEY`) flows natively through the sandbox.

#### 3. Transparent Fail-Safe Decorators
Flow scripts are automatically scanned and patched with `@trace_flow()` decorators on execution. To guarantee that this decoration never blocks runtime execution:
* The embedded `tracing` wrapper imports `langfuse` using a silent try/catch block.
* If `langfuse` keys are not set, or the library is unavailable in a bare environment, the decorator gracefully translates into a silent, zero-overhead **no-op wrapper**.
* You can write code assuming tracing is *always present*—no more missing import or script crash warnings!

---

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

### 3. 🔍 Decoupled Native Tracing with Langfuse
The harness **automatically** injects professional Langfuse tracing into your workflows natively.

To make tracing completely straightforward, zero-config, and deep:
1. **Decoupled Bundling**: Both the `pocketflow` core engine and the `tracing` modules are embedded natively inside the extension and auto-populated into every task sandbox (`.pi/pocketflow/<task_name>/tracing`). There are **no manual outer file reads**, no local file imports required, and no package-install requirements.
2. **Dual-Level Telemetry (Workflow & Model-Level)**:
   - **Level A (Workflow & Graph Level)**: Captured automatically by the pre-compiled `@trace_flow()` flow-class decorator injected by the harness. This maps your entire flow execution start/end times and records the exact input, output, execution state, and results for each node phase (`prep`, `exec`, and `post` phases) as nested child spans of the main Flow trace.
   - **Level B (Model & LLM Level)**: When using OpenAI, Instructor (`get_instructor_client()`), or other supported packages, the underlying client libraries auto-instrument themselves. They submit distinct model-level entries to Langfuse containing prompt text, completions, model names, and detailed token/pricing usages.
   This dual-layer mapping ensures both your graph logic and and your underlying LLM API usage are recorded with high-fidelity side-by-side!
3. **Graceful Fail-Safe**: If Langfuse credentials (`LANGFUSE_SECRET_KEY` and `LANGFUSE_PUBLIC_KEY`) are missing or tracing is disabled in your terminal `.env`, the pre-bundled tracer automatically converts into a silent, overhead-free no-op. It guarantees consistent execution without environment import crashes.

No manual instrumentation, decorating, or extra package setup is necessary. Just instantiate your standard `Flow` or `AsyncFlow` and run it:

```python
# ✅ CLEAN AND STANDARD (The harness automatically injects decorators @trace_flow to log all executions)
class MyEpicJourneyFlow(Flow):
    def __init__(self):
        node_a = MyNode()
        super().__init__(start=node_a)
```

You will see active flow and step tracing output in stdout and inside your Langfuse dashboard showing full performance breakdowns of your runs when following this pattern.n following this pattern.

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
