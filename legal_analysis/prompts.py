# prompts.py
STRUCTURED_PROMPT = """
You are a senior legal analyst. You will be given a document chunk and must identify risks, categorize severity, and provide legal recommendations.

Return ONLY a JSON object that matches this schema exactly (no extra commentary):

{
  "doc_id": "<id>",
  "chunk_id": "<id>",
  "risks": [
    {
      "risk_id": "<id>",
      "title": "<one-line title>",
      "severity": "low|medium|high",
      "confidence": 0.0,
      "evidence": "<text excerpt from source>",
      "explanation": "<2-3 sentence explanation>",
      "recommendation": "<concise legal action or mitigation step>"
    }
  ],
  "summary": "<one-paragraph summary>",
  "meta": {"model":"<name>", "prompt_version":"structured-v1"}
}

Now analyze the chunk below. Only use evidence present in the chunk. If no risk is present, return "risks": [] and a short summary.

CHUNK:
<<<DOCUMENT_CHUNK>>>
"""

# helper to fill prompt
def build_structured_prompt(doc_id, chunk_id, chunk):
    return STRUCTURED_PROMPT.replace("<<<DOCUMENT_CHUNK>>>", chunk)
