# legal_analysis/analyze_routes.py

from flask import Blueprint, request, jsonify
from tika import parser
from utils.ollama_client import call_llm

legal_analysis_bp = Blueprint("legal_analysis", __name__, url_prefix="/legal")

@legal_analysis_bp.route("/analyze", methods=["POST"])
def analyze_contract():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    parsed = parser.from_buffer(file.read())
    text = parsed.get("content", "")

    if not text.strip():
        return jsonify({"error": "Could not extract text"}), 400

    prompt = f"""
Summarize this legal contract into clear, precise bullet points.
Focus on:
- Parties involved
- Term & duration
- Payment terms
- Obligations
- Termination clauses
- Confidentiality
- Governing law

Contract:
{text}

Summary:
"""

    summary = call_llm("mistral-large-latest", prompt)

    return jsonify({"summary": summary})
