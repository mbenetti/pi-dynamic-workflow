import os
from typing import Literal, Optional

from pydantic import BaseModel, Field
from utils import DOCS, call_llm, get_instructor_client

from pocketflow import Node, StructuredNode


class DecideSchema(BaseModel):
    action: Literal["read", "answer"] = Field(
        description="Whether to read another document or answer the question"
    )
    doc: Optional[str] = Field(
        default=None, description="The document name to read next, if action is read"
    )


class DecideAction(StructuredNode):
    def __init__(self):
        model = "gpt-4o" if os.environ.get("OPENAI_API_KEY") else "gemini-2.0-flash"
        super().__init__(
            response_model=DecideSchema,
            client=get_instructor_client(),
            model=model,
        )

    def prep(self, shared):
        """Read the question, accumulated context, and available doc names."""
        question = shared["question"]
        context = shared.get("context", "")
        available = list(DOCS.keys())

        prompt = f"""You are an agentic RAG assistant. You have access to a set of documents about PocketFlow.
Your job is to decide whether you have enough context to answer the question, or if you need to read another document.

Question: {question}
Available documents: {available}
Context already gathered: {context if context else "nothing yet"}

If you have enough information to answer the question, set action to 'answer'.
Otherwise, pick one document to read next.
"""
        return prompt

    def post(self, shared, prep_res, exec_res):
        """Route to 'read' or 'answer' based on the LLM decision."""
        decision = exec_res.model_dump()
        if decision["action"] == "read":
            shared["doc_to_read"] = decision.get("doc", "")
            print(f"  🔍 Agent decides to read '{shared['doc_to_read']}'")
        else:
            print(f"  💡 Agent decides it has enough context to answer")
        return decision["action"]


class ReadDoc(Node):
    def prep(self, shared):
        """Get the document name to read."""
        return shared["doc_to_read"]

    def exec(self, doc_name):
        """Retrieve the document content from the store."""
        print(f"  📄 Reading document: {doc_name}")
        return DOCS.get(doc_name, "Document not found.")

    def post(self, shared, prep_res, exec_res):
        """Append the document content to the accumulated context."""
        shared["context"] = shared.get("context", "") + f"\n[{prep_res}]: {exec_res}"
        print(f"  ✅ Added '{prep_res}' to context")
        return "decide"


class Answer(Node):
    def prep(self, shared):
        """Get the question and accumulated context."""
        return shared["question"], shared.get("context", "")

    def exec(self, inputs):
        """Generate the final answer using the accumulated context."""
        question, context = inputs
        print(f"  ✍️ Generating answer...")
        return call_llm(
            f"Based on this context:\n{context}\n\nAnswer the following question concisely and accurately: {question}"
        )

    def post(self, shared, prep_res, exec_res):
        """Store the final answer."""
        shared["answer"] = exec_res
