import json
import os
import subprocess
import urllib.request
import ollama
from pydantic import BaseModel
from pocketflow import Node
from liteparse import LiteParse

class PaperFeatures(BaseModel):
    authors: list[str]
    keywords: list[str]

class FetchPapersNode(Node):
    def prep(self, shared):
        return {
            "limit": shared.get("limit", 10)
        }

    def exec(self, prep_res):
        limit = prep_res["limit"]
        cmd = ["hf", "papers", "list", "--limit", str(limit), "--format", "json"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        papers = json.loads(res.stdout)
        return papers

    def post(self, shared, prep_res, exec_res):
        shared["papers"] = exec_res
        return "default"

class DownloadPDFsNode(Node):
    def prep(self, shared):
        return {
            "papers": shared.get("papers", []),
            "download_dir": shared.get("download_dir", "./pdf_downloads")
        }

    def exec(self, prep_res):
        papers = prep_res["papers"]
        download_dir = prep_res["download_dir"]
        os.makedirs(download_dir, exist_ok=True)
        
        downloaded = []
        for p in papers:
            paper_id = p.get("id")
            if not paper_id:
                continue
            pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
            dest = os.path.join(download_dir, f"{paper_id}.pdf")
            try:
                # Standard User-Agent header
                req = urllib.request.Request(
                    pdf_url, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
                )
                with urllib.request.urlopen(req) as resp:
                    with open(dest, 'wb') as f:
                        f.write(resp.read())
                downloaded.append({
                    "id": paper_id,
                    "title": p.get("title", ""),
                    "local_path": dest
                })
                print(f"Downloaded PDF for {paper_id}")
            except Exception as e:
                print(f"Failed to download PDF for {paper_id}: {e}")
        return downloaded

    def post(self, shared, prep_res, exec_res):
        shared["downloaded_files"] = exec_res
        return "default"

class ExtractFirstPageOllamaNode(Node):
    def prep(self, shared):
        return {
            "downloaded_files": shared.get("downloaded_files", []),
            "model": shared.get("ollama_model", "lfm2.5:latest")
        }

    def exec(self, prep_res):
        downloaded_files = prep_res["downloaded_files"]
        model_name = prep_res["model"]
        
        # Disable OCR and extract page 1 only 
        parser = LiteParse(target_pages="1", ocr_enabled=False)
        
        results = []
        for item in downloaded_files:
            file_path = item["local_path"]
            paper_id = item["id"]
            title = item["title"]
            print(f"Extracting first page and querying Ollama for: {paper_id}")
            
            try:
                # Parse first page text
                parse_res = parser.parse(file_path)
                first_page_text = parse_res.text
                
                # Query Ollama with Structured Output constraint using schema
                prompt = (
                    f"You are given the first page of an academic paper. "
                    f"Please extract the exact authors list and main keywords list. "
                    f"If authors are not found but there are names, list them. "
                    f"Here is the text:\n\n{first_page_text}"
                )
                
                res = ollama.chat(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    format=PaperFeatures.model_json_schema()
                )
                
                extracted_data = json.loads(res.message.content)
                authors = extracted_data.get("authors", [])
                keywords = extracted_data.get("keywords", [])
                
                results.append({
                    "id": paper_id,
                    "title": title,
                    "authors": authors,
                    "keywords": keywords,
                    "arxiv_url": f"https://arxiv.org/abs/{paper_id}"
                })
            except Exception as e:
                print(f"Error processing paper {paper_id}: {e}")
                results.append({
                    "id": paper_id,
                    "title": title,
                    "authors": [],
                    "keywords": [],
                    "arxiv_url": f"https://arxiv.org/abs/{paper_id}",
                    "error": str(e)
                })
        return results

    def post(self, shared, prep_res, exec_res):
        shared["extracted_papers"] = exec_res
        return "default"

class GenerateMarkdownNode(Node):
    def prep(self, shared):
        return {
            "extracted_papers": shared.get("extracted_papers", []),
            "output_path": shared.get("output_path", "./papers_and_authors.md")
        }

    def exec(self, prep_res):
        extracted_papers = prep_res["extracted_papers"]
        output_path = prep_res["output_path"]
        
        lines = [
            "# Academic Papers Summary Report",
            f"Generated automatically on 2026-06-12",
            f"Total papers processed: {len(extracted_papers)}",
            "",
            "| Title | Authors | Keywords | arXiv Link |",
            "|---|---|---|---|",
        ]
        
        for paper in extracted_papers:
            title = paper["title"].replace("\n", " ").replace("|", "\\|")
            authors = ", ".join(paper["authors"]) if paper["authors"] else "N/A"
            keywords = ", ".join(paper["keywords"]) if paper["keywords"] else "N/A"
            link = f"[{paper['id']}]({paper['arxiv_url']})"
            lines.append(f"| {title} | {authors} | {keywords} | {link} |")
            
        lines.append("")
        lines.append("## Detailed Paper Summaries")
        lines.append("")
        for paper in extracted_papers:
            title = paper["title"].replace("\n", " ")
            lines.append(f"### {title}")
            lines.append(f"- **arXiv ID**: {paper['id']}")
            lines.append(f"- **arXiv URL**: {paper['arxiv_url']}")
            
            authors_str = ", ".join(paper["authors"]) if paper["authors"] else "*None extracted*"
            lines.append(f"- **Authors (Extracted)**: {authors_str}")
            
            keywords_str = ", ".join(paper["keywords"]) if paper["keywords"] else "*None extracted*"
            lines.append(f"- **Keywords (Extracted)**: {keywords_str}")
            lines.append("")
            lines.append("---")
            lines.append("")
            
        markdown_content = "\n".join(lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        return output_path

    def post(self, shared, prep_res, exec_res):
        shared["final_report_path"] = exec_res
        return "default"
