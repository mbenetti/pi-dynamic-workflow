---
name: hf-paper-scraper
description: Automated weekly academic paper scraper and summarizer that uses the Hugging Face Hub CLI list/search endpoints combined with Rust-native LiteParse to locally extract complete abstracts without API tokens or cloud limits.
---

# Hugging Face Paper Scraper Skill

Use this skill when the user asks to look up, search, list, compile, or summarize academic papers or research articles from Hugging Face Papers or ArXiv, particularly when doing domain-specific research or weekly compilations.

---

## 🎨 Recommended Implementation Pattern

To achieve production-grade speed, complete local extraction, and respect remote rate-limits, you should always design a dynamic PocketFlow workflow utilizing the **Hugging Face Hub CLI (`hf papers`)** for querying, and **`liteparse`** for local, offline extraction.

### Core Architectural Architecture
1. **Query via HF CLI**: Use `hf papers search "query" --limit N --format json` in a parent subprocess. It is native to the workstation, up-to-date, and returns clean structured metadata.
2. **Download & Cache Locally**: Always download the PDF files into a local cache directory (`hf_papers_downloads/`) using standard `urllib` before parsing. *Never stream remote URLs directly into a parser* as this violates arXiv's anti-crawling policies and lacks local retry caching.
3. **Rust-Native Local Parsing**: Initialize LlamaIndex's Rust-native `liteparse` with `ocr_enabled=False` for lightning-fast, local spatial PDF parsing.
4. **Complete Abstract Carving**: Use robust regex boundaries to isolate and carve out **only the complete Abstract section** of the PDF.

---

## 🚀 PocketFlow Template Blueprint

When creating a dynamic pipeline with `execute_pocketflow_workflow`, copy and adapt this standard blueprint:

### 1. `nodes.py` definition:
```python
import os
import subprocess
import json
import re
import urllib.request
from pocketflow import Node

class FetchHFPapersNode(Node):
    """Natively executes hf papers command to find target papers."""
    def prep(self, shared):
        return {
            "query": shared.get("search_query", "agents"),
            "limit": shared.get("limit_papers", 10)
        }

    def exec(self, prep_res):
        query = prep_res["query"]
        limit = prep_res["limit"]
        
        # Use hf CLI which is reliably installed and has auto-upvotes data
        cmd = ["hf", "papers", "search", query, "--limit", str(limit), "--format", "json"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        
        papers = []
        for p in data:
            papers.append({
                "id": p.get("id"),
                "title": p.get("title")
            })
        return papers

    def post(self, shared, prep_res, exec_res):
        shared["papers"] = exec_res
        return "default"


class DownloadPDFsNode(Node):
    """Caches PDFs locally to prevent arXiv rate-limiting bans."""
    def prep(self, shared):
        return {
            "papers": shared.get("papers", []),
            "download_dir": shared.get("download_dir", "./hf_downloads")
        }

    def exec(self, prep_res):
        papers = prep_res["papers"]
        download_dir = prep_res["download_dir"]
        os.makedirs(download_dir, exist_ok=True)
        
        downloaded = []
        for p in papers:
            paper_id = p["id"]
            pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
            dest = os.path.join(download_dir, f"{paper_id}.pdf")
            try:
                req = urllib.request.Request(pdf_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as resp:
                    with open(dest, 'wb') as f:
                        f.write(resp.read())
                downloaded.append({
                    "id": paper_id,
                    "title": p["title"],
                    "local_path": dest
                })
            except Exception as e:
                print(f"Skipping {paper_id} due to rate limits or download failure: {e}")
        return downloaded

    def post(self, shared, prep_res, exec_res):
        shared["downloaded_files"] = exec_res
        return "default"


class ExtractAbstractsNode(Node):
    """Decodes local PDF using native liteparse and parses the abstract block."""
    def prep(self, shared):
        return {
            "downloaded_files": shared.get("downloaded_files", []),
            "output_file": shared.get("output_file", "./weekly_summary.md")
        }

    def exec(self, prep_res):
        from liteparse import LiteParse
        downloaded_files = prep_res["downloaded_files"]
        output_file = prep_res["output_file"]
        
        # ocr_enabled=False makes liteparse run in local native C/Rust mode
        parser = LiteParse(ocr_enabled=False)
        
        content = [
            f"# HF Papers Report - Abstract Summary",
            f"Generated locally using LiteParse via Agent Scraper Skill.",
            f"Total parsed papers: {len(downloaded_files)}",
            ""
        ]
        
        for p in downloaded_files:
            try:
                res = parser.parse(p["local_path"])
                full_text = res.text
                
                # Rigid extraction targeting complete Abstract
                match = re.search(r'(?i)(abstract)[\s\S]*?(?=(1\.?\s+)?\s*(introduction))', full_text)
                abstract = match.group(0).strip() if match else " ".join(full_text.split("\n")[:15])
                abstract = re.sub(r'\s+', ' ', abstract)
            except Exception as e:
                abstract = f"Error extracting abstract: {e}"
                
            content.append(f"## [{p['id']}] {p['title']}")
            content.append(f"**arXiv URL**: [https://arxiv.org/abs/{p['id']}](https://arxiv.org/abs/{p['id']})")
            content.append(f"\n> **Abstract**: {abstract}\n")
            content.append("---\n")
            
        full_markdown = "\n".join(content)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(full_markdown)
        return output_file

    def post(self, shared, prep_res, exec_res):
        shared["output_file_written"] = exec_res
        return "default"
```

### 2. `flow.py` definition:
```python
from pocketflow import Flow
from nodes import FetchHFPapersNode, DownloadPDFsNode, ExtractAbstractsNode

class PDFScraperFlow(Flow):
    def __init__(self):
        fetch = FetchHFPapersNode()
        dl = DownloadPDFsNode()
        ext = ExtractAbstractsNode()
        
        fetch >> dl >> ext
        super().__init__(start=fetch)
```

### 3. `main.py` definition:
```python
from flow import PDFScraperFlow

if __name__ == "__main__":
    flow = PDFScraperFlow()
    shared = {
        "search_query": "agents",
        "limit_papers": 5,
        "output_file": "./my_weekly_summary.md"
    }
    flow.run(shared)
```

---

## 🔍 Best-Practice Extraction Guidelines
1. **Never use standard PDF libraries like PyPDF/PDFPlumber**: They cannot handle complex column configurations and suffer on mathematical spacing. LiteParse uses native C-PDFium compiled bindings, rendering text layout-faithfully.
2. **Never turn OCR on by default**: OCR introduces a huge performance penalty (Tesseract cold start). Leave `ocr_enabled=False` since academic papers already store underlying digital text directly.
3. **Graceful Failbacks**: Some papers may group headings differently (e.g. index terms before introduction). Always provide a paragraph-slice fallback when headings regex fails.
