import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { resolve, dirname, delimiter } from "node:path";
import { promises as fs } from "node:fs";
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
      "Decoupled Langfuse Tracing: PocketFlow core engine and Langfuse tracing modules are pre-bundled natively inside the harness! Always write flow classes decorated with @trace_flow() without installing additional libraries or packages manually. You don't need any local files of 'pocketflow-tracing'. Tracing will quietly initialize and execute without errors even if credentials or tracing are disabled in the host environment.",
      "Traceable Provenance: Always populate the 'original_query' and 'thinking_process' fields when calling this tool. This ensures the design intent and architectural decisions are preserved inside the sandbox workspace for future audits.",
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
      original_query: Type.Optional(Type.String({
        description: "The raw user prompt or developer intent behind this workflow execution.",
      })),
      thinking_process: Type.Optional(Type.String({
        description: "The architectural reasoning, node planning, and trade-offs compiled by the agent.",
      })),
    }),

    async execute(toolCallId, params, signal, onUpdate, ctx) {
      const taskDir = resolve(ctx.cwd, `.pi/pocketflow/${params.task_name}`).replace(/[\\/]/g, "/");

      try {
        // Step A: Create temporary directory for the workflow
        onUpdate?.({
          content: [
            { type: "text", text: "📁 Creating workflow directory..." },
          ],
        });
        await fs.mkdir(taskDir, { recursive: true });
        await fs.mkdir(resolve(taskDir, "utils"), { recursive: true });

        // Clean process.env to prevent virtualenv contamination from parent shells
        if (process.env.VIRTUAL_ENV) {
          delete process.env.VIRTUAL_ENV;
        }
        if (process.env.PATH) {
          process.env.PATH = process.env.PATH.split(delimiter)
            .filter(p => !p.includes("pocketflow-tracing"))
            .join(delimiter);
        }

        // Load the .env file strictly from the current working directory as specified by the user
        const parsedEnv: Record<string, string> = {};
        try {
          const envPath = resolve(ctx.cwd, ".env");
          try {
            const fileContent = await fs.readFile(envPath, "utf8");
            for (const line of fileContent.split(/\r?\n/)) {
              const trimmed = line.trim();
              if (trimmed && !trimmed.startsWith("#")) {
                const parts = trimmed.split("=");
                if (parts.length >= 2) {
                  const key = parts[0].trim();
                  let val = parts.slice(1).join("=").trim();
                  const commentIdx = val.indexOf("#");
                  if (commentIdx !== -1) {
                    const hasOpenQuote = (val.match(/'/g) || []).length % 2 !== 0 || (val.match(/"/g) || []).length % 2 !== 0;
                    if (!hasOpenQuote) {
                      val = val.substring(0, commentIdx).trim();
                    }
                  }
                  parsedEnv[key] = val.replace(/^['"]|['"]$/g, "");
                }
              }
            }
            // Copy/write the file to the task directory so python-dotenv in the subprocess loads it!
            await fs.writeFile(resolve(taskDir, ".env"), fileContent, "utf8");
          } catch (err) {
            // file doesn't exist or read error, ignore
          }
        } catch (e) {
          // Ignore
        }

        // Step B: Check for Langfuse environment variables on the host
        const hasLangfuse = !!(
          (parsedEnv.LANGFUSE_SECRET_KEY || parsedEnv.LANGFUSE_API_KEY || process.env.LANGFUSE_SECRET_KEY || process.env.LANGFUSE_API_KEY) &&
          (parsedEnv.LANGFUSE_PUBLIC_KEY || process.env.LANGFUSE_PUBLIC_KEY)
        );

        // Check if uv is available on the machine or fallback
        let useUv = false;
        let uvPath = "uv";
        try {
          const isWin = process.platform === "win32";
          await execAsync(isWin ? "where uv" : "which uv");
          useUv = true;
        } catch (e) {
          // Check if "uv" resides globally by trying to execute "uv --version"
          try {
            await execAsync("uv --version");
            useUv = true;
          } catch (uvErr) {
            // Keep false
          }
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
            lines.append(f"\\n    subgraph subgraph_flow_{get_id(node)}[{type(node).__name__}]")
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

        // TRACING PACKAGE SOURCE CODE EMBEDDED NATIVELY FOR THE SANDBOX
        const tracingInitSource = `"""
PocketFlow Tracing Module
"""
from .config import TracingConfig
from .core import LangfuseTracer
from .decorator import trace_flow

__all__ = ["trace_flow", "TracingConfig", "LangfuseTracer"]
`;

        const tracingConfigSource = `import os
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv
    dotenv_available = True
except ImportError:
    dotenv_available = False

@dataclass
class TracingConfig:
    langfuse_secret_key: Optional[str] = None
    langfuse_public_key: Optional[str] = None
    langfuse_host: Optional[str] = None
    debug: bool = False
    trace_inputs: bool = True
    trace_outputs: bool = True
    trace_prep: bool = True
    trace_exec: bool = True
    trace_post: bool = True
    trace_errors: bool = True
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    
    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "TracingConfig":
        if dotenv_available:
            # Load specifically from the active folder's copied .env rather than global shell or root CWD!
            # Since config.py lives under tracing/config.py, we go up two levels to get the workspace directory.
            task_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            if os.path.exists(task_env_path):
                load_dotenv(dotenv_path=task_env_path, override=True)
            else:
                load_dotenv(override=True)

        return cls(
            langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY") or os.getenv("LANGFUSE_API_KEY"),
            langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            langfuse_host=os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com",
            debug=os.getenv("POCKETFLOW_TRACING_DEBUG", "false").lower() == "true",
            trace_inputs=os.getenv("POCKETFLOW_TRACE_INPUTS", "true").lower() == "true",
            trace_outputs=os.getenv("POCKETFLOW_TRACE_OUTPUTS", "true").lower() == "true",
            trace_prep=os.getenv("POCKETFLOW_TRACE_PREP", "true").lower() == "true",
            trace_exec=os.getenv("POCKETFLOW_TRACE_EXEC", "true").lower() == "true",
            trace_post=os.getenv("POCKETFLOW_TRACE_POST", "true").lower() == "true",
            trace_errors=os.getenv("POCKETFLOW_TRACE_ERRORS", "true").lower() == "true",
            session_id=os.getenv("POCKETFLOW_SESSION_ID") or os.getenv("LANGFUSE_SESSION_ID"),
            user_id=os.getenv("POCKETFLOW_USER_ID") or os.getenv("LANGFUSE_USER_ID")
        )
        
    def validate(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)
`;

        const tracingCoreSource = `import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

from .config import TracingConfig

class LangfuseTracer:
    def __init__(self, config: TracingConfig):
        self.config = config
        self.client = None
        self.current_trace = None
        self.spans = {}
        
        if LANGFUSE_AVAILABLE and config.validate():
            try:
                kwargs = {}
                if config.langfuse_secret_key:
                    kwargs["secret_key"] = config.langfuse_secret_key
                if config.langfuse_public_key:
                    kwargs["public_key"] = config.langfuse_public_key
                if config.langfuse_host:
                    kwargs["host"] = config.langfuse_host
                self.client = Langfuse(**kwargs)
            except Exception as e:
                pass

    def start_trace(self, flow_name: str, input_data: Dict[str, Any]) -> Optional[str]:
        if not self.client:
            return None
        try:
            self.current_trace = self.client.trace(
                name=flow_name,
                input=self._serialize_data(input_data),
                metadata={
                    "framework": "PocketFlow",
                    "trace_type": "flow_execution",
                    "timestamp": datetime.now().isoformat(),
                },
                session_id=self.config.session_id,
                user_id=self.config.user_id,
            )
            return self.current_trace.id
        except Exception:
            return None

    def end_trace(self, output_data: Dict[str, Any], status: str = "success") -> None:
        if not self.current_trace:
            return
        try:
            self.current_trace.update(
                output=self._serialize_data(output_data),
                metadata={
                    "status": status,
                    "end_timestamp": datetime.now().isoformat(),
                },
            )
        except Exception:
            pass
        finally:
            self.current_trace = None
            self.spans.clear()

    def start_node_span(self, node_name: str, node_id: str, phase: str) -> Optional[str]:
        if not self.current_trace:
            return None
        try:
            span_id = f"{node_id}_{phase}"
            span = self.current_trace.span(
                name=f"{node_name}.{phase}",
                metadata={
                    "node_type": node_name,
                    "node_id": node_id,
                    "phase": phase,
                    "start_timestamp": datetime.now().isoformat(),
                },
            )
            self.spans[span_id] = span
            return span_id
        except Exception:
            return None

    def end_node_span(self, span_id: str, input_data: Any = None, output_data: Any = None, error: Exception = None) -> None:
        if span_id not in self.spans:
            return
        try:
            span = self.spans[span_id]
            update_data = {}
            if input_data is not None and self.config.trace_inputs:
                update_data["input"] = self._serialize_data(input_data)
            if output_data is not None and self.config.trace_outputs:
                update_data["output"] = self._serialize_data(output_data)
                
            if error and self.config.trace_errors:
                update_data.update({
                    "level": "ERROR",
                    "status_message": str(error),
                    "metadata": {
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                        "end_timestamp": datetime.now().isoformat(),
                    }
                })
            else:
                update_data.update({
                    "level": "DEFAULT",
                    "metadata": {"end_timestamp": datetime.now().isoformat()},
                })
            span.update(**update_data)
            span.end()
        except Exception:
            pass
        finally:
            if span_id in self.spans:
                del self.spans[span_id]

    def _serialize_data(self, data: Any) -> Any:
        try:
            if hasattr(data, "__dict__"):
                return {"_type": type(data).__name__, "_data": str(data)}
            elif isinstance(data, (dict, list, str, int, float, bool, type(None))):
                return data
            return {"_type": type(data).__name__, "_data": str(data)}
        except Exception:
            return {"_type": "unknown", "_data": "<serialization_failed>"}

    def flush(self) -> None:
        if self.client:
            try:
                self.client.flush()
            except Exception:
                pass
`;

        const tracingDecoratorSource = `import functools
import inspect
import uuid
import time
from typing import Optional
from .config import TracingConfig
from .core import LangfuseTracer

def trace_flow(
    config: Optional[TracingConfig] = None,
    flow_name: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None
):
    def decorator(flow_class_or_func):
        if inspect.isclass(flow_class_or_func):
            return _trace_flow_class(flow_class_or_func, config, flow_name, session_id, user_id)
        return _trace_flow_function(flow_class_or_func, config, flow_name, session_id, user_id)
    return decorator

def _trace_flow_class(flow_class, config, flow_name, session_id, user_id):
    if config is None:
        config = TracingConfig.from_env()
    if session_id:
        config.session_id = session_id
    if user_id:
        config.user_id = user_id
    if flow_name is None:
        flow_name = flow_class.__name__
        
    original_init = flow_class.__init__
    original_run = getattr(flow_class, 'run', None)
    original_run_async = getattr(flow_class, 'run_async', None)
    
    def traced_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._tracer = LangfuseTracer(config)
        self._flow_name = flow_name
        self._trace_id = None
        self._patch_nodes()
        
    def traced_run(self, shared):
        if not hasattr(self, '_tracer'):
            return original_run(self, shared) if original_run else None
        self._trace_id = self._tracer.start_trace(self._flow_name, shared)
        try:
            result = original_run(self, shared) if original_run else None
            self._tracer.end_trace(shared, "success")
            return result
        except Exception as e:
            self._tracer.end_trace(shared, "error")
            raise
        finally:
            self._tracer.flush()
            if self._tracer.client:
                # Give background threads a small moment to flush all batched events over the container network before standard exit
                time.sleep(0.5)

    async def traced_run_async(self, shared):
        if not hasattr(self, '_tracer'):
            return await original_run_async(self, shared) if original_run_async else None
        self._trace_id = self._tracer.start_trace(self._flow_name, shared)
        try:
            result = await original_run_async(self, shared) if original_run_async else None
            self._tracer.end_trace(shared, "success")
            return result
        except Exception as e:
            self._tracer.end_trace(shared, "error")
            raise
        finally:
            self._tracer.flush()
            if self._tracer.client:
                # Give background threads a small moment to flush all batched events over the container network before standard exit
                time.sleep(0.5)
            
    def patch_nodes(self):
        start_nd = getattr(self, 'start_node', None) or getattr(self, '_start_node', None)
        if not start_nd:
            return
        visited = set()
        nodes_to_patch = [start_nd]
        while nodes_to_patch:
            node = nodes_to_patch.pop(0)
            if id(node) in visited:
                continue
            visited.add(id(node))
            self._patch_node(node)
            if hasattr(node, 'successors'):
                for successor in node.successors.values():
                    if successor and id(successor) not in visited:
                        nodes_to_patch.append(successor)
                        
    def patch_node(self, node):
        if hasattr(node, '_pocketflow_traced'):
            return
        node_id = str(uuid.uuid4())
        node_name = type(node).__name__
        original_prep = getattr(node, 'prep', None)
        original_exec = getattr(node, 'exec', None)
        original_post = getattr(node, 'post', None)
        original_prep_async = getattr(node, 'prep_async', None)
        original_exec_async = getattr(node, 'exec_async', None)
        original_post_async = getattr(node, 'post_async', None)
        
        if original_prep:
            node.prep = self._create_traced_method(original_prep, node_id, node_name, 'prep')
        if original_exec:
            node.exec = self._create_traced_method(original_exec, node_id, node_name, 'exec')
        if original_post:
            node.post = self._create_traced_method(original_post, node_id, node_name, 'post')
        if original_prep_async:
            node.prep_async = self._create_traced_async_method(original_prep_async, node_id, node_name, 'prep')
        if original_exec_async:
            node.exec_async = self._create_traced_async_method(original_exec_async, node_id, node_name, 'exec')
        if original_post_async:
            node.post_async = self._create_traced_async_method(original_post_async, node_id, node_name, 'post')
            
        node._pocketflow_traced = True
        
    def create_traced_method(self, original_method, node_id, node_name, phase):
        @functools.wraps(original_method)
        def traced_method(*args, **kwargs):
            span_id = self._tracer.start_node_span(node_name, node_id, phase)
            try:
                result = original_method(*args, **kwargs)
                self._tracer.end_node_span(span_id, input_data=args, output_data=result)
                return result
            except Exception as e:
                self._tracer.end_node_span(span_id, input_data=args, error=e)
                raise
        return traced_method
        
    def create_traced_async_method(self, original_method, node_id, node_name, phase):
        @functools.wraps(original_method)
        async def traced_async_method(*args, **kwargs):
            span_id = self._tracer.start_node_span(node_name, node_id, phase)
            try:
                result = await original_method(*args, **kwargs)
                self._tracer.end_node_span(span_id, input_data=args, output_data=result)
                return result
            except Exception as e:
                self._tracer.end_node_span(span_id, input_data=args, error=e)
                raise
        return traced_async_method
        
    flow_class.__init__ = traced_init
    flow_class._patch_nodes = patch_nodes
    flow_class._patch_node = patch_node
    flow_class._create_traced_method = create_traced_method
    flow_class._create_traced_async_method = create_traced_async_method
    
    if original_run:
        flow_class.run = traced_run
    if original_run_async:
        flow_class.run_async = traced_run_async
        
    return flow_class

def _trace_flow_function(flow_func, config, flow_name, session_id, user_id):
    if config is None:
        config = TracingConfig.from_env()
    if session_id:
        config.session_id = session_id
    if user_id:
        config.user_id = user_id
    if flow_name is None:
        flow_name = flow_func.__name__
        
    tracer = LangfuseTracer(config)
    
    @functools.wraps(flow_func)
    def traced_flow_func(*args, **kwargs):
        shared = args[0] if args else {}
        trace_id = tracer.start_trace(flow_name, shared)
        try:
            result = flow_func(*args, **kwargs)
            tracer.end_trace(shared, "success")
            return result
        except Exception as e:
            tracer.end_trace(shared, "error")
            raise
        finally:
            tracer.flush()
    return traced_flow_func
`;

        // COPY VIZ METADATA GENERATOR SCRIPT INTO TASKDIR FOR DIAGRAM GEN
        let finalFlowCode = params.flow_code;

        // Auto-inject our pre-bundled tracing structure into custom flows automatically regardless of active environment keys
        const destTracingDir = resolve(taskDir, "tracing").replace(/[\\/]/g, "/");
        await fs.mkdir(destTracingDir, { recursive: true });
        await fs.writeFile(resolve(destTracingDir, "__init__.py"), tracingInitSource, "utf8");
        await fs.writeFile(resolve(destTracingDir, "config.py"), tracingConfigSource, "utf8");
        await fs.writeFile(resolve(destTracingDir, "core.py"), tracingCoreSource, "utf8");
        await fs.writeFile(resolve(destTracingDir, "decorator.py"), tracingDecoratorSource, "utf8");

        // Force wrap tracing on all generated flow classes automatically without duplicates!
        if (!finalFlowCode.includes("from tracing import trace_flow") && !finalFlowCode.includes("import trace_flow")) {
          finalFlowCode = "from tracing import trace_flow\n" + finalFlowCode;
        }
        finalFlowCode = finalFlowCode.replace(
          /(@trace_flow\s*\(\s*\)\s*\r?\n\s*)?class\s+(\w+Flow)\((Flow|BatchFlow|AsyncFlow|AsyncBatchFlow|AsyncParallelBatchFlow)\):/g,
          (match, maybeDecorator, className, flowType) => {
            if (maybeDecorator) {
              return match; // Already decorated, do not add it again!
            }
            return `@trace_flow()\nclass ${className}(${flowType}):`;
          }
        );

        // Add Mermaid builder helper to the flow module for diagnostic introspection
        finalFlowCode = finalFlowCode + "\n" + buildMermaidCode;

        await fs.writeFile(
          resolve(taskDir, "nodes.py"),
          params.nodes_code,
          "utf8",
        );
        await fs.writeFile(resolve(taskDir, "flow.py"), finalFlowCode, "utf8");
        await fs.writeFile(resolve(taskDir, "main.py"), params.main_code, "utf8");

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
            ? "from openai import OpenAI\\n\\ndef get_instructor_client():\\n    return instructor.from_openai(OpenAI(base_url='https://openrouter.ai/api/v1', api_key=os.getenv('OPENROUTER_API_KEY')))"
            : "from openai import OpenAI\\n\\ndef get_instructor_client():\\n    return instructor.from_openai(OpenAI(api_key=os.getenv('OPENAI_API_KEY')))";

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

        await fs.writeFile(resolve(taskDir, "utils/__init__.py"), "", "utf8");
        await fs.writeFile(
          resolve(taskDir, "utils/call_llm.py"),
          utilsCode,
          "utf8",
        );

        // Step E: Install any required dependencies
        const allRequirements = [
          "instructor",
          "python-dotenv>=1.0.0",
          ...params.requirements,
        ];
        
        // Always include langfuse package using locked limits matching official cookbooks!
        allRequirements.push("langfuse>=2.0.0");
        allRequirements.push("langfuse<3.0.0");

        // Dynamically auto-inject provider-specific SDKs
        if (activeProvider === "google") {
          allRequirements.push("google-genai");
        } else if (activeProvider === "anthropic") {
          allRequirements.push("anthropic");
        } else if (activeProvider === "openai" || activeProvider === "openrouter") {
          allRequirements.push("openai");
        }

        // Check if main_code contains inline PEP 723 script metadata
        const hasPEPMetadata = /#\s*\/\/\/\s*script/i.test(params.main_code);

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
`
        
        // Write the local pocketflow module directly into the sandbox folder during workflow init
        await fs.mkdir(resolve(taskDir, "pocketflow"), { recursive: true });
        await fs.writeFile(resolve(taskDir, "pocketflow/__init__.py"), pfCoreSource, "utf8");

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
          const isWin = process.platform === "win32";
          const binFolder = isWin ? "Scripts" : "bin";
          const exeSuffix = isWin ? ".exe" : "";
          let pipPath = "pip";
          
          if (process.env.VIRTUAL_ENV) {
            const normVirtualEnv = process.env.VIRTUAL_ENV.replace(/[\\/]/g, "/");
            const possiblePip = resolve(normVirtualEnv, binFolder, `pip${exeSuffix}`).replace(/[\\/]/g, "/");
            const fs = require("node:fs");
            try {
              fs.accessSync(possiblePip);
              pipPath = possiblePip;
            } catch (e) {
              pipPath = "pip";
            }
          }
          const pipExec = pipPath;

          const pipEnv = { ...process.env };
          if (pipEnv.VIRTUAL_ENV) {
            delete pipEnv.VIRTUAL_ENV;
          }
          for (const req of allRequirements) {
            await execAsync(`"${pipExec}" install "${req}"`, { env: pipEnv });
          }
        }

        // Step F: Execute the workflow in a subprocess, forwarding Langfuse environment variables
        onUpdate?.({
          content: [
            { type: "text", text: "🚀 Running PocketFlow workflow..." },
          ],
        });
        ctx.ui.setStatus("pocketflow", "Executing workflow...");

        let execCmd = "";
        if (useUv) {
          // Add --no-cache to bypass Windows cache index / access denied lock issues.
          // Always supply allRequirements via --with flags to ensure minimal packages
          // (such as langfuse or python-dotenv) are loaded even if the script metadata is missing them!
          const withFlags = allRequirements.map(req => `--with "${req}"`).join(" ");
          execCmd = `"${uvPath}" run --no-cache ${withFlags} main.py`;
        } else {
          const isWin = process.platform === "win32";
          const binFolder = isWin ? "Scripts" : "bin";
          const exeSuffix = isWin ? ".exe" : "";
          let pyPath = "python";
          if (process.env.VIRTUAL_ENV) {
            const normVirtualEnv = process.env.VIRTUAL_ENV.replace(/[\\/]/g, "/");
            const possiblePy = resolve(normVirtualEnv, binFolder, `python${exeSuffix}`).replace(/[\\/]/g, "/");
            const fs = require("node:fs");
            try {
              fs.accessSync(possiblePy);
              pyPath = possiblePy;
            } catch (e) {
              pyPath = "python";
            }
          }
          const pythonExec = pyPath;
          execCmd = `"${pythonExec}" main.py`;
        }

        const customEnv: Record<string, string> = {
          ...process.env as Record<string, string>, // Forward host variables
          ...parsedEnv, // Explicitly load latest parsed dotenv variables securely!
          POCKETFLOW_TRACING_DEBUG: parsedEnv.POCKETFLOW_TRACING_DEBUG || process.env.POCKETFLOW_TRACING_DEBUG || "false",
          PYTHONPATH: taskDir, // Ensure task directory is on PYTHONPATH so local pocketflow can be imported securely!
        };
        // Avoid setting empty strings as they contaminate and override python load_dotenv behaviour
        const hostVal = parsedEnv.LANGFUSE_BASE_URL || parsedEnv.LANGFUSE_HOST || process.env.LANGFUSE_BASE_URL || process.env.LANGFUSE_HOST;
        if (hostVal) {
          customEnv.LANGFUSE_HOST = hostVal;
        }
        if (customEnv.VIRTUAL_ENV) {
          delete customEnv.VIRTUAL_ENV;
        }

        const { stdout, stderr } = await execAsync(execCmd, {
          cwd: taskDir,
          timeout: 60000, // 1 minute timeout
          maxBuffer: 25 * 1024 * 1024, // 25MB buffer
          env: customEnv,
        });

        // Step G: Dynamic Mermaid blueprint visualization injection if configured
        const wantVisualize = true; // FORCE VISUALIZATION OUTPUT AS REQUESTED BY USER
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
            await fs.writeFile(resolve(taskDir, "_introspect_graph.py"), introspectorScript, "utf8");

            const isWin = process.platform === "win32";
            const binFolder = isWin ? "Scripts" : "bin";
            const exeSuffix = isWin ? ".exe" : "";
            let pPath = "python";
            if (process.env.VIRTUAL_ENV) {
              const normVirtualEnv = process.env.VIRTUAL_ENV.replace(/[\\/]/g, "/");
              const possiblePy = resolve(normVirtualEnv, binFolder, `python${exeSuffix}`).replace(/[\\/]/g, "/");
              const fs = require("node:fs");
              try {
                fs.accessSync(possiblePy);
                pPath = possiblePy;
              } catch (e) {
                pPath = "python";
              }
            }
            // Since we are running the introspection script with uv, we need to make sure 
            // that the subdirectory 'pocketflow' inside taskDir can be loaded properly.
            // Let's copy it or link it so 'import pocketflow' inside introspect engine works cleanly if using uv!
            // When using "uv run", it executes within taskDir but may need an empty python project setup or package requirements if it fails due to resolving.
            // Actually, we can run "uv run python _introspect_graph.py" to utilize the local directory's python packages properly!
            let introspectCmd = "";
            if (useUv) {
              if (hasPEPMetadata) {
                introspectCmd = `"${uvPath}" run --no-cache _introspect_graph.py`;
              } else {
                const withFlags = allRequirements.map(req => `--with "${req}"`).join(" ");
                introspectCmd = `"${uvPath}" run --no-cache ${withFlags} _introspect_graph.py`;
              }
            } else {
              introspectCmd = `"${pPath}" _introspect_graph.py`;
            }

            const introspectEnv = { ...process.env };
            if (introspectEnv.VIRTUAL_ENV) {
              delete introspectEnv.VIRTUAL_ENV;
            }
            const introspectRes = await execAsync(introspectCmd, { cwd: taskDir, env: introspectEnv });
            await fs.writeFile(resolve(taskDir, "_introspect_debug.log"), `STDOUT:\n${introspectRes.stdout}\n\nSTDERR:\n${introspectRes.stderr}`, "utf8");
            console.log("INTROSPECT OUT:", introspectRes.stdout);
            console.log("INTROSPECT ERR:", introspectRes.stderr);
            const match = introspectRes.stdout.match(/===START_BLUEPRINT===([\s\S]*?)===END_BLUEPRINT===/);
            if (match && match[1]) {
              const diagramText = match[1].trim();
              
              // Compile Provenance Metadata elements
              const queryBlock = params.original_query 
                ? `## 🎯 Original Prompt / Architectural Intent\n\n> ${params.original_query.trim().replace(/\n/g, "\n> ")}\n\n`
                : "";
                
              const thinkingBlock = params.thinking_process
                ? `## 🧠 Architectural Thinking Process & Design Choices\n\n${params.thinking_process.trim()}\n\n`
                : "";

              const blueprintMd = `# Workflow Blueprint: ${params.task_name}\n\nGenerated automatically via PocketFlow recursive visualization engine.\n\n${queryBlock}${thinkingBlock}## Topology Diagram\n\n\`\`\`mermaid\n${diagramText}\n\`\`\`\n\n## 📄 Workspace Source Code Auditing\n\n### \`nodes.py\`\n\n\`\`\`python\n${params.nodes_code.trim()}\n\`\`\`\n\n### \`flow.py\`\n\n\`\`\`python\n${params.flow_code.trim()}\n\`\`\`\n\n### \`main.py\`\n\n\`\`\`python\n${params.main_code.trim()}\n\`\`\`\n`;
        // Write blueprint cleanly to an isolated md file inside the workspace
        // Let's print the blueprint diagram to stderr/stdout so it is visible in the result output, as well as saving!
        console.log("WROTE BLUEPRINT DIAGRAM: ", diagramText);
        // Force the output path to end in blueprint.md, cleanly resolved against ctx.cwd
        const customBlueprintPath = resolve(ctx.cwd, `${params.task_name}_blueprint.md`).replace(/[\\/]/g, "/");
        await fs.writeFile(customBlueprintPath, blueprintMd, "utf8");
        
        // Also save a copy directly inside the sandbox taskDir so it propagates permanently !
        await fs.writeFile(resolve(taskDir, "PROVENANCE.md"), blueprintMd, "utf8");
        
        ctx.ui.notify(`Workspace blueprint and provenance saved to ${params.task_name}_blueprint.md`, "info");
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
