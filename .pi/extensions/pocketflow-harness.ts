import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { resolve, dirname } from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { exec } from "node:child_process";
import { promisify } from "node:util";

const execAsync = promisify(exec);

export default function (pi: ExtensionAPI) {
  // Store active model and provider dynamically
  let activeModelId = "google/gemini-3.5-flash";
  let activeProvider = "openrouter";

  // Listen to model selection events to keep in sync with Pi agent
  pi.on("model_select", async (event, ctx) => {
    if (event.model) {
      activeModelId = event.model.id;
      activeProvider = event.model.provider;
      ctx.ui.notify(
        `PocketFlow Harness synced with model: ${activeProvider}/${activeModelId}`,
        "info",
      );
    }
  });

  // Notify user on session start
  pi.on("session_start", async (_event, ctx) => {
    ctx.ui.notify("PocketFlow Dynamic Harness Extension Loaded!", "info");
  });

  // Register the Custom Tool for the Pi Agent
  pi.registerTool({
    name: "execute_pocketflow_workflow",
    label: "Execute PocketFlow Workflow",
    description:
      "Generates and executes a multi-step PocketFlow workflow on the fly to solve a complex task.",
    promptSnippet: "Execute a dynamic multi-step workflow using PocketFlow",
    promptGuidelines: [
      "Use execute_pocketflow_workflow when a task requires multiple sequential steps, web scraping, data extraction, or parallel batch processing.",
      "Provide the complete Python code for nodes.py, flow.py, and main.py in the parameters.",
      "CRITICAL: Always instantiate a Flow or AsyncFlow using the parameter name 'start' (e.g., Flow(start=first_node)). Do NOT use 'start_node=first_node', as it is unsupported and will raise a TypeError.",
      "CRITICAL: The post/post_async method in any Node MUST return a string action key (e.g., 'default', 'success', 'failure') and update the shared state in-place. Do NOT return the shared dictionary itself.",
      "The generated nodes should import from 'utils.call_llm' to call the LLM or get the instructor client.",
      "Ensure all nodes are connected sequence-wise (e.g., node_a >> node_b >> node_c) and return a Flow wrapping the start node using start=node_a.",
      "Always define Pydantic schemas for structured nodes to guarantee clean data contracts between nodes.",
    ],
    parameters: Type.Object({
      task_name: Type.String({
        description: "A short slug for the task (e.g., pricing_comparison)",
      }),
      nodes_code: Type.String({
        description:
          "The complete Python code for nodes.py defining the PocketFlow Nodes.",
      }),
      flow_code: Type.String({
        description:
          "The complete Python code for flow.py connecting the nodes.",
      }),
      main_code: Type.String({
        description:
          "The complete Python code for main.py initializing shared state and running the flow.",
      }),
      requirements: Type.Array(Type.String(), {
        description:
          "List of pip packages required for this workflow (e.g., ['beautifulsoup4', 'httpx']).",
      }),
    }),

    async execute(toolCallId, params, signal, onUpdate, ctx) {
      const taskDir = resolve(ctx.cwd, `.pi/pocketflow/${params.task_name}`);

      try {
        // Step A: Create temporary directory for the workflow
        onUpdate?.({
          content: [
            { type: "text", text: "📁 Creating workflow directory..." },
          ],
        });
        await mkdir(taskDir, { recursive: true });
        await mkdir(resolve(taskDir, "utils"), { recursive: true });

        // Load .env files from multiple possible locations so it works from any folder
        try {
          const dotenv = require("dotenv");
          // 1. Try loading from current working directory (.env)
          dotenv.config({ path: resolve(ctx.cwd, ".env"), override: true });
          // 2. Try loading from current working directory's PocketFlow folder (PocketFlow/.env)
          dotenv.config({ path: resolve(ctx.cwd, "PocketFlow/.env"), override: true });
          // 3. Try loading relative to the extension's directory as a fallback
          dotenv.config({ path: resolve(__dirname, "../../PocketFlow/.env"), override: true });
        } catch (e) {
          // Ignore if dotenv is not installed or files don't exist
        }

        // Step B: Check for Langfuse environment variables on the host
        const hasLangfuse = !!(
          (process.env.LANGFUSE_SECRET_KEY || process.env.LANGFUSE_API_KEY) && 
          process.env.LANGFUSE_PUBLIC_KEY
        );

        let useUv = false;
        let uvPath = "uv";
        try {
          await execAsync("which uv");
          useUv = true;
        } catch (e) {
          // Fall back to standard python/pip
        }

        // COPY VIZ METADATA GENERATOR SCRIPT INTO TASKDIR FOR DIAGRAM GEN
        const buildMermaidCode = `
import inspect
from pocketflow import Flow

def build_mermaid(start):
    ids, visited, lines = {}, set(), ["graph LR"]
    ctr = 1
    def get_id(n):
        nonlocal ctr
        return ids[n] if n in ids else (ids.setdefault(n, f"N{ctr}"), (ctr := ctr + 1))[0]
    def link(a, b):
        lines.append(f"    {a} --> {b}")
    def walk(node, parent=None):
        if node in visited:
            return parent and link(parent, get_id(node))
        visited.add(node)
        if isinstance(node, Flow):
            node_start = getattr(node, "start_node", None) or getattr(node, "_start_node", None)
            node_start and parent and link(parent, get_id(node_start))
            lines.append(f"\\n    subgraph sub_flow_{get_id(node)}[{type(node).__name__}]")
            node_start and walk(node_start)
            for nxt in node.successors.values():
                node_start and walk(nxt, get_id(node_start)) or (parent and link(parent, get_id(nxt))) or walk(nxt)
            lines.append("    end\\n")
        else:
            lines.append(f"    {(nid := get_id(node))}['{type(node).__name__}']")
            parent and link(parent, nid)
            [walk(nxt, nid) for nxt in node.successors.values()]
    walk(start)
    return "\\n".join(lines)
`;

        // COPY VIZ METADATA GENERATOR SCRIPT INTO TASKDIR FOR DIAGRAM GEN
        let finalFlowCode = params.flow_code;

        // Step C: If Langfuse configured, inject automated tracing into flow.py
        if (hasLangfuse) {
          // Copy target tracing directory to our temporary execute directory
          const srcTracingDir = resolve(
            ctx.cwd,
            "PocketFlow/cookbook/pocketflow-tracing/tracing",
          );
          const destTracingDir = resolve(taskDir, "tracing");
          await execAsync(`cp -r "${srcTracingDir}" "${destTracingDir}"`);

          // Inject the trace_flow import and decorator into flow.py
          finalFlowCode = "from tracing import trace_flow\n" + finalFlowCode;
          finalFlowCode = finalFlowCode.replace(
            /class\s+(\w+Flow)\((Flow|BatchFlow|AsyncFlow|AsyncBatchFlow|AsyncParallelBatchFlow)\):/g,
            "@trace_flow()\nclass $1($2):",
          );
        }

        // Add Mermaid builder helper to the flow module for diagnostic introspection
        finalFlowCode = finalFlowCode + "\n" + buildMermaidCode;

        await writeFile(
          resolve(taskDir, "nodes.py"),
          params.nodes_code,
          "utf8",
        );
        await writeFile(resolve(taskDir, "flow.py"), finalFlowCode, "utf8");
        await writeFile(resolve(taskDir, "main.py"), params.main_code, "utf8");

        // Step D: Dynamically generate utils/call_llm.py to match the Pi agent's active model and provider
        onUpdate?.({
          content: [{ type: "text", text: "⚙️ Configuring LLM utilities..." }],
        });
        let utilsCode = "";
        if (activeProvider === "google") {
          utilsCode = `import os
import instructor
from google import genai

def get_instructor_client():
    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY", ""),
    )
    return instructor.from_genai(client)

def call_llm(prompt):
    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY", ""),
    )
    response = client.models.generate_content(
        model="${activeModelId}",
        contents=[prompt]
    )
    return response.text
`;
        } else if (activeProvider === "openai") {
          utilsCode = `import os
import instructor
from openai import OpenAI

def get_instructor_client():
    if os.getenv("OPENROUTER_API_KEY"):
        return instructor.from_openai(OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        ))
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    return instructor.from_openai(client)

def call_llm(prompt):
    if os.getenv("OPENROUTER_API_KEY"):
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
    else:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    response = client.chat.completions.create(
        model="${activeModelId}",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content
`;
        } else if (activeProvider === "openrouter") {
          utilsCode = `import os
import instructor
from openai import OpenAI

def get_instructor_client():
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY", "")
    )
    return instructor.from_openai(client)

def call_llm(prompt):
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY", "")
    )
    response = client.chat.completions.create(
        model="${activeModelId}",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content
`;
        } else if (activeProvider === "anthropic") {
          utilsCode = `import os
import instructor
from anthropic import Anthropic

def get_instructor_client():
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    return instructor.from_anthropic(client)

def call_llm(prompt):
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    response = client.messages.create(
        model="${activeModelId}",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text
`;
        } else {
          // Fallback to OpenRouter or OpenAI client
          const apiKey = process.env.OPENROUTER_API_KEY
            ? process.env.OPENROUTER_API_KEY
            : process.env.OPENAI_API_KEY || "";
          const baseUrl = process.env.OPENROUTER_API_KEY
            ? "from openai import OpenAI\n\ndef get_instructor_client():\n    return instructor.from_openai(OpenAI(base_url='https://openrouter.ai/api/v1', api_key=os.getenv('OPENROUTER_API_KEY')))"
            : "from openai import OpenAI\n\ndef get_instructor_client():\n    return instructor.from_openai(OpenAI(api_key=os.getenv('OPENAI_API_KEY')))";

          utilsCode = `import os
import instructor
from openai import OpenAI

def get_instructor_client():
    if os.getenv("OPENROUTER_API_KEY"):
        return instructor.from_openai(OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        ))
    return instructor.from_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY", "")))

def call_llm(prompt):
    if os.getenv("OPENROUTER_API_KEY"):
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
    else:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

    response = client.chat.completions.create(
        model="${activeModelId}",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content
`;
        }

        await writeFile(resolve(taskDir, "utils/__init__.py"), "", "utf8");
        await writeFile(
          resolve(taskDir, "utils/call_llm.py"),
          utilsCode,
          "utf8",
        );

        // Step E: Install any required dependencies
        const allRequirements = [
          "instructor",
          "pydantic>=2.0.0",
          "python-dotenv>=1.0.0",
          ...params.requirements,
        ];
        if (hasLangfuse) {
          allRequirements.push("langfuse>=2.0.0");
          allRequirements.push("langfuse<3.0.0");
        }

        // DYNAMIC POCKETFLOW CORE ENGINE INJECTION
        // This injects the exact 200-line PocketFlow core directly into the sandbox folder,
        // making the generated workspace 100% self-contained, skipping remote pip dependencies 
        // entirely, and preventing version incompatibilities or resolution lags.
        const pfCoreSource = `import asyncio
import copy
import time
import warnings

class BaseNode:
    def __init__(self):
        self.params, self.successors = {}, {}

    def set_params(self, params):
        self.params = params

    def next(self, node, action="default"):
        if action in self.successors:
            warnings.warn(f"Overwriting successor for action '{action}'")
        self.successors[action] = node
        return node

    def prep(self, shared):
        pass

    def exec(self, prep_res):
        pass

    def post(self, shared, prep_res, exec_res):
        pass

    def _exec(self, prep_res):
        return self.exec(prep_res)

    def _run(self, shared):
        p = self.prep(shared)
        e = self._exec(p)
        return self.post(shared, p, e)

    def run(self, shared):
        if self.successors:
            warnings.warn("Node won't run successors. Use Flow.")
        return self._run(shared)

    def __rshift__(self, other):
        return self.next(other)

    def __sub__(self, action):
        if isinstance(action, str):
            return _ConditionalTransition(self, action)
        raise TypeError("Action must be a string")

class _ConditionalTransition:
    def __init__(self, src, action):
        self.src, self.action = src, action

    def __rshift__(self, tgt):
        return self.src.next(tgt, self.action)

class Node(BaseNode):
    def __init__(self, max_retries=1, wait=0):
        super().__init__()
        self.max_retries, self.wait = max_retries, wait

    def exec_fallback(self, prep_res, exc):
        raise exc

    def _exec(self, prep_res):
        for self.cur_retry in range(self.max_retries):
            try:
                return self.exec(prep_res)
            except Exception as e:
                if self.cur_retry == self.max_retries - 1:
                    return self.exec_fallback(prep_res, e)
                if self.wait > 0:
                    time.sleep(self.wait)

class BatchNode(Node):
    def _exec(self, items):
        return [super(BatchNode, self)._exec(i) for i in (items or [])]

class Flow(BaseNode):
    def __init__(self, start=None):
        super().__init__()
        self.start_node = start

    def start(self, start):
        self.start_node = start
        return start

    def get_next_node(self, curr, action):
        nxt = curr.successors.get(action or "default")
        if not nxt and curr.successors:
            warnings.warn(f"Flow ends: '{action}' not found in {list(curr.successors)}")
        return nxt

    def _orch(self, shared, params=None):
        curr, p, last_action = (
            copy.copy(self.start_node),
            (params or {**self.params}),
            None,
        )
        while curr:
            curr.set_params(p)
            last_action = curr._run(shared)
            curr = copy.copy(self.get_next_node(curr, last_action))
        return last_action

    def _run(self, shared):
        p = self.prep(shared)
        o = self._orch(shared)
        return self.post(shared, p, o)

    def post(self, shared, prep_res, exec_res):
        return exec_res

class BatchFlow(Flow):
    def _run(self, shared):
        pr = self.prep(shared) or []
        for bp in pr:
            self._orch(shared, {**self.params, **bp})
        return self.post(shared, pr, None)

class AsyncNode(Node):
    async def prep_async(self, shared):
        pass

    async def exec_async(self, prep_res):
        pass

    async def exec_fallback_async(self, prep_res, exc):
        raise exc

    async def post_async(self, shared, prep_res, exec_res):
        pass

    async def _exec(self, prep_res):
        for self.cur_retry in range(self.max_retries):
            try:
                return await self.exec_async(prep_res)
            except Exception as e:
                if self.cur_retry == self.max_retries - 1:
                    return await self.exec_fallback_async(prep_res, e)
                if self.wait > 0:
                    await asyncio.sleep(self.wait)

    async def run_async(self, shared):
        if self.successors:
            warnings.warn("Node won't run successors. Use AsyncFlow.")
        return await self._run_async(shared)

    async def _run_async(self, shared):
        p = await self.prep_async(shared)
        e = await self._exec(p)
        return await self.post_async(shared, p, e)

    def _run(self, shared):
        raise RuntimeError("Use run_async.")

class AsyncBatchNode(AsyncNode, BatchNode):
    async def _exec(self, items):
        return [await super(AsyncBatchNode, self)._exec(i) for i in items]

class AsyncParallelBatchNode(AsyncNode, BatchNode):
    async def _exec(self, items):
        return await asyncio.gather(
            *(super(AsyncParallelBatchNode, self)._exec(i) for i in items)
        )

class AsyncFlow(Flow, AsyncNode):
    async def _orch_async(self, shared, params=None):
        curr, p, last_action = (
            copy.copy(self.start_node),
            (params or {**self.params}),
            None,
        )
        while curr:
            curr.set_params(p)
            last_action = (
                await curr._run_async(shared)
                if isinstance(curr, AsyncNode)
                else curr._run(shared)
            )
            curr = copy.copy(self.get_next_node(curr, last_action))
        return last_action

    async def _run_async(self, shared):
        p = await self.prep_async(shared)
        o = await self._orch_async(shared)
        return await self.post_async(shared, p, o)

    async def post_async(self, shared, prep_res, exec_res):
        return exec_res

class AsyncBatchFlow(AsyncFlow, BatchFlow):
    async def _run_async(self, shared):
        pr = await self.prep_async(shared) or []
        for bp in pr:
            await self._orch_async(shared, {**self.params, **bp})
        return await self.post_async(shared, pr, None)

class AsyncParallelBatchFlow(AsyncFlow, BatchFlow):
    async def _run_async(self, shared):
        pr = await self.prep_async(shared) or []
        await asyncio.gather(
            *(self._orch_async(shared, {**self.params, **bp}) for bp in pr)
        )
        return await self.post_async(shared, pr, None)

class StructuredNode(Node):
    def __init__(self, response_model, client, model="gpt-4o", max_retries=3, wait=0):
        super().__init__(max_retries=max_retries, wait=wait)
        self.response_model = response_model
        self.client = client
        self.model = model

    def exec(self, prep_res):
        if isinstance(prep_res, str):
            kwargs = {"messages": [{"role": "user", "content": prep_res}]}
        elif isinstance(prep_res, list):
            kwargs = {"messages": prep_res}
        elif isinstance(prep_res, dict):
            kwargs = prep_res
        else:
            raise TypeError("prep_res must be a str, list, or dict")

        if "model" not in kwargs:
            kwargs["model"] = self.model
        if "response_model" not in kwargs:
            kwargs["response_model"] = self.response_model

        return self.client.create(**kwargs)

class AsyncStructuredNode(AsyncNode):
    def __init__(self, response_model, client, model="gpt-4o", max_retries=3, wait=0):
        super().__init__(max_retries=max_retries, wait=wait)
        self.response_model = response_model
        self.client = client
        self.model = model

    async def exec_async(self, prep_res):
        if isinstance(prep_res, str):
            kwargs = {"messages": [{"role": "user", "content": prep_res}]}
        elif isinstance(prep_res, list):
            kwargs = {"messages": prep_res}
        elif isinstance(prep_res, dict):
            kwargs = prep_res
        else:
            raise TypeError("prep_res must be a str, list, or dict")

        if "model" not in kwargs:
            kwargs["model"] = self.model
        if "response_model" not in kwargs:
            kwargs["response_model"] = self.response_model

        return await self.client.create(**kwargs)
`;
        
        // Write the local pocketflow module directly into the sandbox folder during workflow init
        await mkdir(resolve(taskDir, "pocketflow"), { recursive: true });
        await writeFile(resolve(taskDir, "pocketflow/__init__.py"), pfCoreSource, "utf8");

        // Check if uv is available on the machine for instant on-the-fly execution (already detected above)

        if (useUv) {
          onUpdate?.({
            content: [
              {
                type: "text",
                text: `⚡ Fast running with isolated on-the-fly dependencies using UV...`,
              },
            ],
          });
        } else {
          onUpdate?.({
            content: [
              {
                type: "text",
                text: `📦 Installing dependencies: ${allRequirements.join(", ")}...`,
              },
            ],
          });
          ctx.ui.setStatus("pocketflow", "Installing dependencies...");
          const pipExec = process.env.VIRTUAL_ENV
            ? await execAsync(
                `test -f "${resolve(process.env.VIRTUAL_ENV, "bin/pip")}"`,
              )
                .then(() => resolve(process.env.VIRTUAL_ENV!, "bin/pip"))
                .catch(() => resolve(process.env.VIRTUAL_ENV!, "bin/pip3"))
            : "pip";

          for (const req of allRequirements) {
            await execAsync(`"${pipExec}" install "${req}"`);
          }
        }

        // Step F: Execute the workflow in a subprocess, forwarding Langfuse environment variables
        onUpdate?.({
          content: [
            { type: "text", text: "🚀 Running PocketFlow workflow..." },
          ],
        });
        ctx.ui.setStatus("pocketflow", "Executing workflow...");

        // Load .env files from multiple possible locations so they are inherited by the subprocess
        try {
          const dotenv = require("dotenv");
          dotenv.config({ path: resolve(ctx.cwd, ".env"), override: true });
          dotenv.config({ path: resolve(ctx.cwd, "PocketFlow/.env"), override: true });
          dotenv.config({ path: resolve(__dirname, "../../PocketFlow/.env"), override: true });
        } catch (e) {
          // Ignore
        }

        let execCmd = "";
        if (useUv) {
          // run instantly on-the-fly with isolated dependencies
          const withFlags = allRequirements.map(req => `--with "${req}"`).join(" ");
          execCmd = `"${uvPath}" run ${withFlags} main.py`;
        } else {
          const pythonExec = process.env.VIRTUAL_ENV
            ? resolve(process.env.VIRTUAL_ENV, "bin/python")
            : "python";
          execCmd = `"${pythonExec}" main.py`;
        }

        const { stdout, stderr } = await execAsync(execCmd, {
          cwd: taskDir,
          timeout: 60000, // 1 minute timeout
          maxBuffer: 25 * 1024 * 1024, // 25MB buffer
          env: {
            ...process.env, // Forward all host environment variables
            POCKETFLOW_TRACING_DEBUG: process.env.POCKETFLOW_TRACING_DEBUG || "false", // Use host value if set, fallback to silent
            LANGFUSE_HOST:
              process.env.LANGFUSE_BASE_URL || process.env.LANGFUSE_HOST || "",
          },
        });

        // Step G: Dynamic Mermaid blueprint visualization injection if configured
        const wantVisualize = (process.env.POCKETFLOW_VISUALIZE || "false").toLowerCase() === "true";
        if (wantVisualize) {
          try {
            // Write a temporary introspector engine inside our task-dir
            const introspectorScript = `
import importlib
import sys
import os
import inspect

sys.path.append(os.path.abspath("."))
import flow
from flow import build_mermaid

# Find the flow wrapper class automatically
flow_classes = [obj for name, obj in inspect.getmembers(flow, inspect.isclass) 
                if issubclass(obj, flow.Flow) and obj != flow.Flow]

if flow_classes:
    flow_class = flow_classes[0]
    flow_instance = flow_class()
    mermaid_diagram = build_mermaid(flow_instance)
    print("===START_BLUEPRINT===")
    print(mermaid_diagram)
    print("===END_BLUEPRINT===")
`;
            // Append temporary introspector metadata run
            await writeFile(resolve(taskDir, "_introspect_graph.py"), introspectorScript, "utf8");

            const introspectCmd = useUv 
              ? `"${uvPath}" run --with "pocketflow" _introspect_graph.py`
              : `"${process.env.VIRTUAL_ENV ? resolve(process.env.VIRTUAL_ENV, "bin/python") : "python"}" _introspect_graph.py`;

            const introspectRes = await execAsync(introspectCmd, { cwd: taskDir });
            const match = introspectRes.stdout.match(/===START_BLUEPRINT===([\s\S]*?)===END_BLUEPRINT===/);
            if (match && match[1]) {
              const diagramText = match[1].trim();
              const blueprintMd = `# Workflow Blueprint: ${params.task_name}\n\nGenerated automatically via PocketFlow recursive visualization engine.\n\n## Topology Diagram\n\n\`\`\`mermaid\n${diagramText}\n\`\`\`\n\n## 📄 Workspace Source Code Auditing\n\n### \`nodes.py\`\n\n\`\`\`python\n${params.nodes_code.trim()}\n\`\`\`\n\n### \`flow.py\`\n\n\`\`\`python\n${params.flow_code.trim()}\n\`\`\`\n\n### \`main.py\`\n\n\`\`\`python\n${params.main_code.trim()}\n\`\`\`\n`;
              // Write blueprint cleanly to an isolated md file inside the workspace
              await writeFile(resolve(ctx.cwd, `${params.task_name}_blueprint.md`), blueprintMd, "utf8");
              ctx.ui.notify(`Workspace blueprint saved to ${params.task_name}_blueprint.md`, "info");
            }
          } catch (e: any) {
            // Silence visualizer fallback error quietly
          }
        }

        // Clear status
        ctx.ui.setStatus("pocketflow", undefined);

        return {
          content: [
            {
              type: "text",
              text: `### Workflow Execution Successful\n\n**Stdout:**\n\`\`\`\n${stdout}\n\`\`\``,
            },
          ],
          details: { stdout, stderr, success: true },
        };
      } catch (error: any) {
        ctx.ui.setStatus("pocketflow", undefined);
        ctx.ui.notify(`Workflow execution failed: ${error.message}`, "error");

        // Return the error traceback back to Gemini for self-healing
        throw new Error(
          `Workflow execution failed.\n\n**Error:**\n${error.message}\n\n**Stderr:**\n${error.stderr || ""}\n\n**Stdout:**\n${error.stdout || ""}`,
        );
      }
    },
  });

  // 4. Register a Slash Command for manual runs
  pi.registerCommand("pocketflow", {
    description: "Manage or run PocketFlow dynamic workflows",
    handler: async (args, ctx) => {
      ctx.ui.notify(
        `PocketFlow Harness CLI: ${args || "No arguments provided"}`,
        "info",
      );
    },
  });
}
