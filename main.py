# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "liteparse",
#     "pydantic>=2.0.0",
#     "ollama",
#     "pocketflow"
# ]
# ///

from flow import HFPapersWorkflowFlow

if __name__ == "__main__":
    workflow = HFPapersWorkflowFlow()
    shared = {
        "limit": 10,
        "download_dir": "./pdf_downloads",
        "ollama_model": "lfm2.5:latest",
        "output_path": "./papers_and_authors.md"
    }
    workflow.run(shared)
    print("Workflow run completed successfully inside the uv runtime!")
    print(f"Final output: {shared.get('final_report_path')}")
