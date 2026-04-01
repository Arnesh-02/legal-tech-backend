# analyzer.py
import json
from .infer import generate_with_model, extract_json_from_text
from .prompts import build_structured_prompt

def analyze_chunks(chunks, doc_id, model_name):
    """
    For each chunk, call the model and parse JSON. Returns list of dicts.
    Each returned item:
      {"doc_id":..., "chunk_id": i, "model": model_name, "latency": float,
       "raw_text": "<raw model output>", "parsed": <parsed dict or error dict>}
    """
    results = []
    for i, chunk in enumerate(chunks):
        prompt = build_structured_prompt(doc_id, i, chunk)
        out_text, latency = generate_with_model(prompt, model_name)
        parsed = extract_json_from_text(out_text)

        # ensure doc_id + chunk_id in parsed for traceability
        if isinstance(parsed, dict):
            parsed.setdefault("doc_id", doc_id)
            parsed.setdefault("chunk_id", str(i))
            parsed.setdefault("meta", {})
            parsed["meta"].setdefault("model", model_name)
        else:
            parsed = {"parse_error": True, "raw": out_text, "doc_id": doc_id, "chunk_id": str(i)}

        results.append({
            "doc_id": doc_id,
            "chunk_id": i,
            "model": model_name,
            "latency": latency,
            "raw_text": out_text,
            "parsed": parsed
        })
    return results
