import os
import wave
from typing import List, Literal

from pydantic import BaseModel, Field
from utils import DOCS, call_llm, get_instructor_client, text_to_speech

from pocketflow import Node, StructuredNode

VOICES = {"Alex": "alloy", "Jamie": "echo"}


class ScriptLineSchema(BaseModel):
    name: Literal["Alex", "Jamie"] = Field(description="Name of the speaker")
    line: str = Field(description="The line spoken by the speaker")


class ScriptSchema(BaseModel):
    script: List[ScriptLineSchema] = Field(
        description="List of script lines in conversational order"
    )


class AnalyzeDocs(Node):
    def prep(self, shared):
        """Read documents from the shared store."""
        return shared.get("docs", DOCS)

    def exec(self, docs):
        """Extract interesting nuggets from each document."""
        all_docs = "\n\n---\n\n".join(
            f"Document {i + 1}:\n{doc}" for i, doc in enumerate(docs)
        )
        prompt = (
            "Extract 2-3 surprising or interesting nuggets from EACH document. "
            "Focus on things that would make someone say 'wait, really?'\n\n"
            f"{all_docs}"
        )
        return call_llm(prompt)

    def post(self, shared, prep_res, exec_res):
        shared["nuggets"] = exec_res
        print(f"  🔍 Extracted nuggets from {len(prep_res)} documents")


class WriteScript(StructuredNode):
    def __init__(self):
        super().__init__(
            response_model=ScriptSchema, client=get_instructor_client(), model="gpt-4o"
        )

    def prep(self, shared):
        """Read the extracted nuggets."""
        nuggets = shared["nuggets"]
        prompt = f"""Write a podcast script between two hosts: Alex and Jamie.

Source nuggets:
{nuggets}

Write ~6 exchanges (12 lines). Make it natural, with reactions and interruptions.
"""
        return prompt

    def post(self, shared, prep_res, exec_res):
        shared["script"] = [item.model_dump() for item in exec_res.script]
        print(f"  ✍️  Generated script with {len(shared['script'])} lines")
        for item in shared["script"]:
            print(
                f"    {item['name']}: {item['line'][:80]}{'...' if len(item['line']) > 80 else ''}"
            )


class TextToSpeech(Node):
    def prep(self, shared):
        """Read the podcast script."""
        return shared["script"]

    def exec(self, script):
        """Convert each line of the script to speech and concatenate."""
        audio_parts = []
        for i, item in enumerate(script):
            voice = VOICES.get(item["name"], "alloy")
            print(
                f"    🎙️  Generating audio for {item['name']} (line {i + 1}/{len(script)})..."
            )
            audio_data = text_to_speech(item["line"], voice=voice)
            audio_parts.append(audio_data)
        return b"".join(audio_parts)

    def post(self, shared, prep_res, exec_res):
        # Detect format: MP3 starts with ID3 or 0xff; otherwise raw PCM from Gemini
        is_mp3 = exec_res[:3] == b"ID3" or (len(exec_res) > 1 and exec_res[0] == 0xFF)
        if is_mp3:
            out = shared.get("output_file", "podcast.mp3")
            with open(out, "wb") as f:
                f.write(exec_res)
        else:
            # Raw PCM from Gemini TTS — wrap in WAV (24kHz, 16-bit, mono)
            out = os.path.splitext(shared.get("output_file", "podcast.mp3"))[0] + ".wav"
            with wave.open(out, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(exec_res)
        shared["audio_file"] = out
        print(f"  ✅ Audio saved to {out}")
