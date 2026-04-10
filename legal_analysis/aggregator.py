# aggregator.py
from sentence_transformers import SentenceTransformer, util
import uuid
import numpy as np

# load model once
_embed_model = None
def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _embed_model

def dedupe_and_merge(parsed_chunk_results, similarity_threshold=0.82):
    """
    parsed_chunk_results: list of dicts from analyzer.analyze_chunks -> each item contains parsed JSON with 'risks'
    Returns aggregated final JSON for whole document.
    """
    embed_model = _get_embed_model()
    # collect all risk entries
    all_risks = []
    for item in parsed_chunk_results:
        parsed = item["parsed"]
        chunk_id = item["chunk_id"]
        if isinstance(parsed, dict) and "risks" in parsed:
            for r in parsed["risks"]:
                r_copy = r.copy()
                r_copy["_source_chunk"] = chunk_id
                all_risks.append(r_copy)

    if not all_risks:
        print("[WARNING] No risks were found in any chunk by the LLM.")
        return {"risks": [], "meta": {}}

    texts = [ (r.get("title","") + " " + r.get("evidence","")) for r in all_risks ]
    embeddings = embed_model.encode(texts, convert_to_tensor=True)

    clusters = []
    used = set()
    for i in range(len(all_risks)):
        if i in used: continue
        # start cluster with i
        sim = util.cos_sim(embeddings[i], embeddings).cpu().numpy()[0]
        idxs = [j for j, s in enumerate(sim) if s >= similarity_threshold]
        for j in idxs:
            used.add(j)
        # merge cluster
        cluster_items = [all_risks[j] for j in idxs]
        # heuristic merge: choose title of highest confidence if present
        def conf(r):
            return float(r.get("confidence", 0.0))
        cluster_items_sorted = sorted(cluster_items, key=conf, reverse=True)
        primary = cluster_items_sorted[0]
        merged = {
            "risk_id": "R-" + uuid.uuid4().hex[:8],
            "title": primary.get("title"),
            "severity": primary.get("severity"),
            "confidence": max(conf(r) for r in cluster_items),
            "evidence": "; ".join([r.get("evidence","") for r in cluster_items if r.get("evidence")]),
            "explanation": primary.get("explanation"),
            "recommendation": primary.get("recommendation"),
            "sources": [{"chunk": r.get("_source_chunk")} for r in cluster_items]
        }
        clusters.append(merged)
    return {"risks": clusters, "meta": {"num_input_risks": len(all_risks), "num_merged": len(clusters)}}
