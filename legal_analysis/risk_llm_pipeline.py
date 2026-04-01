# risk_llm_pipeline.py
import os
import uuid

from .pdf_extract import extract_text_from_pdf
from .chunker import chunk_text
from .analyzer import analyze_chunks
from .aggregator import dedupe_and_merge

def run_risk_analysis(pdf_path: str):
    """
    Runs the entire LLM pipeline:
    1. Extract text
    2. Chunk text
    3. Run analysis using LLM (via infer.py)
    4. Merge risks
    """
    doc_id = "DOC-" + uuid.uuid4().hex[:8]

    # 1. Extract text
    text = extract_text_from_pdf(pdf_path)
    if not text or not text.strip():
        raise ValueError("No text extracted from PDF")

    # 2. Chunk
    chunks = chunk_text(text)

    # 3. Analyze with model
    analysis = analyze_chunks(chunks, doc_id, model_name="mistral")

    # 4. Aggregate
    aggregated = dedupe_and_merge(analysis)

    aggregated["doc_id"] = doc_id
    aggregated["file_name"] = os.path.basename(pdf_path)

    return aggregated
