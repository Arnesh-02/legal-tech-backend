# redraft/redraft_routes.py

from flask import Blueprint, request, jsonify, send_file
import uuid
from utils.ollama_client import call_llm
from io import BytesIO
from weasyprint import HTML

redraft_bp = Blueprint("redraft", __name__, url_prefix="/redraft")
TASKS = {}


def build_prompt(original_html, instructions):
    return f"""
You are a legal contract redrafting assistant.
Rewrite the HTML contract according to the user's instructions.
But keep the format as such..

Requirements:
- Keep HTML minimal: <html>, <head>, <body>, <h1>/<h2>/<h3>, <p>.
- No styling <div>, <span>, or CSS.
- Keep placeholders like [Company Name], [Founder Name].
- Maintain meaning unless user requests changes.
- Use professional legal language.


User Instructions:
{instructions}

ORIGINAL CONTRACT HTML:
{original_html}

Now produce the updated HTML contract. Output ONLY HTML, NOTHING else.
"""


# redraft/redraft_routes.py (replace redraft() function)
@redraft_bp.route("", methods=["POST"])
def redraft():
    data = request.get_json()
    html = data.get("html")
    instructions = data.get("instructions")

    if not html or not instructions:
        return jsonify({"error": "Missing parameters"}), 400

    task_id = str(uuid.uuid4())
    TASKS[task_id] = {"status": "processing", "result": None}

    prompt = build_prompt(html, instructions)
    updated_html = call_llm("mistral", prompt)
    updated_html = updated_html.replace("```html", "").replace("```", "").strip()

    # Persist result in in-memory TASKS so download endpoint works
    TASKS[task_id] = {"status": "completed", "result": updated_html}

    # Return the HTML immediately so frontend can preview and request PDF
    return jsonify({
        "task_id": task_id,
        "redrafted_html": updated_html
    })

@redraft_bp.route("/status/<task_id>")
def status(task_id):
    return jsonify(TASKS.get(task_id, {"error": "Not found"}))

@redraft_bp.route("/download/<task_id>")
def download(task_id):
    task = TASKS.get(task_id)
    if not task or task["status"] != "completed":
        return jsonify({"error": "Not ready"}), 400

    pdf_stream = BytesIO()
    HTML(string=task["result"]).write_pdf(pdf_stream)
    pdf_stream.seek(0)

    return send_file(
        pdf_stream,
        as_attachment=True,
        download_name="redrafted_contract.pdf",
        mimetype="application/pdf"
    )

@redraft_bp.route("/render_pdf", methods=["POST"])
def render_pdf_from_html():
    """
    Accepts JSON: { "html": "<html>...</html>" }
    Returns: PDF bytes as attachment
    """
    data = request.get_json()
    html = data.get("html")
    if not html:
        return jsonify({"error": "Missing html"}), 400

    pdf_stream = BytesIO()
    HTML(string=html).write_pdf(pdf_stream)
    pdf_stream.seek(0)

    return send_file(
        pdf_stream,
        as_attachment=True,
        download_name="redrafted_contract.pdf",
        mimetype="application/pdf"
    )

