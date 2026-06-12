from pocketflow import Flow
from nodes import FetchPapersNode, DownloadPDFsNode, ExtractFirstPageOllamaNode, GenerateMarkdownNode

class HFPapersWorkflowFlow(Flow):
    def __init__(self):
        fetch = FetchPapersNode()
        dl = DownloadPDFsNode()
        extract = ExtractFirstPageOllamaNode()
        gen_md = GenerateMarkdownNode()
        
        fetch >> dl >> extract >> gen_md
        super().__init__(start=fetch)
