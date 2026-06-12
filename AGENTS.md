# Guidelines for Tool Selection and PocketFlow Workflows

To optimize token usage, maintain conversational speed, and avoid unnecessary complexity, adhere strictly to the following guidelines for utilizing the `execute_pocketflow_workflow` tool:

## 🧭 Tool Selection Philosophy

1. **Standard Mode (Default):**
   - Use built-in tools (`read`, `write`, `edit`, `bash`) for standard tasks like looking up info, editing files, making minor changes, or running simple shell commands.
   - For simple operations, write and execute plain Python scripts via a shell instead of orchestrating a multi-step PocketFlow.

2. **PocketFlow Workflow Mode:**
   - Use `execute_pocketflow_workflow` ONLY when:
     - **Explicitly requested** by the user (e.g., "build a pocketflow workflow for...", "run pocketflow...").
     - **Highly complex orchestration is required**, such as multi-agent debate, parallel scraping/batch processing, complex supervisor-routing loops, or self-healing pipelines with retries.
     - **Context reduction is critical**, i.e., executing a heavy, stateful task inside a sandbox to prevent overloading the main conversation prompt's context window.
