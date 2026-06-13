from typing import Dict, List

from pydantic import BaseModel, Field
from tools.crawler import WebCrawler

from pocketflow import BatchNode, Node, StructuredNode


class AnalysisSchema(BaseModel):
    summary: str = Field(description="A brief summary (2-3 sentences)")
    topics: List[str] = Field(description="Main topics/keywords (up to 5)")
    content_type: str = Field(description="Content type (article, product page, etc)")


class AnalyzePageNode(StructuredNode):
    def __init__(self):
        from utils.call_llm import get_instructor_client

        super().__init__(
            response_model=AnalysisSchema,
            client=get_instructor_client(),
            model="gpt-4o",
        )

    def prep(self, shared):
        # In prep, shared is the webpage content dict
        content = shared
        prompt = f"""
Analyze this webpage content:

Title: {content["title"]}
URL: {content["url"]}
Content: {content["text"][:2000]}  # Limit content length

Please provide:
1. A brief summary (2-3 sentences)
2. Main topics/keywords (up to 5)
3. Content type (article, product page, etc)
"""
        return prompt

    def post(self, shared, prep_res, exec_res):
        return exec_res.model_dump()


class CrawlWebsiteNode(Node):
    """Node to crawl a website and extract content"""

    def prep(self, shared):
        return shared.get("base_url"), shared.get("max_pages", 10)

    def exec(self, inputs):
        base_url, max_pages = inputs
        if not base_url:
            return []

        crawler = WebCrawler(base_url, max_pages)
        return crawler.crawl()

    def post(self, shared, prep_res, exec_res):
        shared["crawl_results"] = exec_res
        return "default"


class AnalyzeContentBatchNode(BatchNode):
    """Node to analyze crawled content in batches"""

    def prep(self, shared):
        results = shared.get("crawl_results", [])
        # Process in batches of 5 pages
        batch_size = 5
        return [results[i : i + batch_size] for i in range(0, len(results), batch_size)]

    def exec(self, batch):
        node = AnalyzePageNode()
        analyzed_results = []
        for content in batch:
            if content and content.get("text"):
                prep_res = node.prep(content)
                exec_res = node.exec(prep_res)
                analysis = node.post(content, prep_res, exec_res)
                content["analysis"] = analysis
                analyzed_results.append(content)
        return analyzed_results

    def post(self, shared, prep_res, exec_res_list):
        # Flatten results from all batches
        all_results = []
        for batch_results in exec_res_list:
            all_results.extend(batch_results)

        shared["analyzed_results"] = all_results
        return "default"


class GenerateReportNode(Node):
    """Node to generate a summary report of the analysis"""

    def prep(self, shared):
        return shared.get("analyzed_results", [])

    def exec(self, results):
        if not results:
            return "No results to report"

        report = []
        report.append(f"Analysis Report\n")
        report.append(f"Total pages analyzed: {len(results)}\n")

        for page in results:
            report.append(f"\nPage: {page['url']}")
            report.append(f"Title: {page['title']}")

            analysis = page.get("analysis", {})
            report.append(f"Summary: {analysis.get('summary', 'N/A')}")
            report.append(f"Topics: {', '.join(analysis.get('topics', []))}")
            report.append(f"Content Type: {analysis.get('content_type', 'unknown')}")
            report.append("-" * 80)

        return "\n".join(report)

    def post(self, shared, prep_res, exec_res):
        shared["report"] = exec_res
        print("\nReport generated:")
        print(exec_res)
        return "default"
