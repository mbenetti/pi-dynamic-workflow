from typing import Dict, List

from pydantic import BaseModel, Field
from tools.search import SearchTool

from pocketflow import Node, StructuredNode


class SearchAnalysisSchema(BaseModel):
    summary: str = Field(
        description="A concise summary of the findings (2-3 sentences)"
    )
    key_points: List[str] = Field(
        description="Key points or facts (up to 5 bullet points)"
    )
    follow_up_queries: List[str] = Field(
        description="Suggested follow-up queries (2-3)"
    )


class SearchNode(Node):
    """Node to perform web search using SerpAPI"""

    def prep(self, shared):
        return shared.get("query"), shared.get("num_results", 5)

    def exec(self, inputs):
        query, num_results = inputs
        if not query:
            return []

        searcher = SearchTool()
        return searcher.search(query, num_results)

    def post(self, shared, prep_res, exec_res):
        shared["search_results"] = exec_res
        return "default"


class AnalyzeResultsNode(StructuredNode):
    """Node to analyze search results using LLM"""

    def __init__(self):
        from utils.call_llm import get_instructor_client

        super().__init__(
            response_model=SearchAnalysisSchema,
            client=get_instructor_client(),
            model="gpt-4o",
        )

    def prep(self, shared):
        query = shared.get("query")
        results = shared.get("search_results", [])
        if not results:
            return {"error": "No search results to analyze"}

        formatted_results = []
        for i, result in enumerate(results, 1):
            formatted_results.append(f"""
Result {i}:
Title: {result["title"]}
Snippet: {result["snippet"]}
URL: {result["link"]}
""")

        prompt = f"""
Analyze these search results for the query: "{query}"

{"\n".join(formatted_results)}

Please provide:
1. A concise summary of the findings (2-3 sentences)
2. Key points or facts (up to 5 bullet points)
3. Suggested follow-up queries (2-3)
"""
        return prompt

    def exec(self, prep_res):
        if isinstance(prep_res, dict) and "error" in prep_res:
            return SearchAnalysisSchema(
                summary=prep_res["error"], key_points=[], follow_up_queries=[]
            )
        return super().exec(prep_res)

    def post(self, shared, prep_res, exec_res):
        analysis = exec_res.model_dump()
        shared["analysis"] = analysis

        # Print analysis
        print("\nSearch Analysis:")
        print("\nSummary:", analysis["summary"])

        print("\nKey Points:")
        for point in analysis["key_points"]:
            print(f"- {point}")

        print("\nSuggested Follow-up Queries:")
        for query in analysis["follow_up_queries"]:
            print(f"- {query}")

        return "default"
