import os
import re
import bcrypt
import tempfile
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv
import json
from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
from gridfs import GridFS
from fpdf import FPDF
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity,
    set_access_cookies, set_refresh_cookies, unset_jwt_cookies
)

from weasyprint import HTML 

from legal_analysis.risk_llm_pipeline import run_risk_analysis

from legal_analysis.infer import generate_with_ollama

# ----------------------------------------------------
# 1. LOAD ENVIRONMENT & CONFIG
# ----------------------------------------------------
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "super-secret-key-development-only")


app = Flask(__name__)

# JWT COOKIE CONFIGURATION
app.config["JWT_SECRET_KEY"] = JWT_SECRET
app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
app.config["JWT_COOKIE_SAMESITE"] = "None"
app.config["JWT_COOKIE_SECURE"] = True
app.config["JWT_ACCESS_COOKIE_PATH"] = '/'
app.config["JWT_REFRESH_COOKIE_PATH"] = '/'
app.config["JWT_COOKIE_CSRF_PROTECT"] = False

jwt = JWTManager(app)

class RiskReportPDF(FPDF):
    def header(self):
        # Professional Header
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(26, 35, 126)  # Your UI's #1a237e blue
        self.cell(0, 10, "CONFIDENTIAL RISK ANALYSIS REPORT", border=0, ln=1, align="L")
        self.set_draw_color(226, 230, 239)
        self.line(10, 20, 200, 20)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(156, 163, 175)
        self.cell(0, 10, f"Page {self.page_no()} | Generated on {datetime.now().strftime('%Y-%m-%d')}", align="C")

def clean_text(text):
    """Sanitizes text for FPDF Helvetica compatibility."""
    if not text: return ""
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2022": "*"
    }
    for u, a in replacements.items():
        text = text.replace(u, a)
    return text.encode("latin-1", "ignore").decode("latin-1")

def create_risk_report(data):
    pdf = RiskReportPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # 1. Title Section
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 15, "Executive Summary", new_x="LMARGIN", new_y="NEXT")
    
    # Metadata Box
    pdf.set_fill_color(249, 250, 251)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(107, 114, 128)
    pdf.cell(0, 8, clean_text(f"  Document Name: {data.get('file_name', 'N/A')}"), border="LT", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, clean_text(f"  Document ID: {data.get('doc_id', 'N/A')}"), border="LB", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)

    # 2. Risk Findings Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(31, 41, 55)
    pdf.cell(0, 10, "Identified Risks & Recommendations", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    for risk in data.get('risks', []):
        severity = risk.get('severity', 'low').lower()
        colors = {
            'high': (220, 38, 38),   # Professional Red
            'medium': (217, 119, 6), # Professional Amber
            'low': (5, 150, 105)     # Professional Green
        }
        r, g, b = colors.get(severity, colors['low'])

        # --- RISK HEADER BLOCK ---
        # Draw a vertical color bar for severity
        curr_y = pdf.get_y()
        pdf.set_fill_color(r, g, b)
        pdf.rect(10, curr_y, 2, 12, 'F') # Thin severity indicator bar
        
        pdf.set_x(14)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(17, 24, 39)
        pdf.multi_cell(0, 6, clean_text(risk.get('title')), ln=1)
        
        # Severity Badge
        pdf.set_x(14)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(r, g, b)
        pdf.cell(0, 5, f"{severity.upper()} SEVERITY | {int(risk.get('confidence', 0)*100)}% CONFIDENCE", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # --- EVIDENCE SECTION ---
        pdf.set_x(14)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(107, 114, 128)
        pdf.cell(0, 5, "EVIDENCE", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_x(14)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(55, 65, 81)
        # Width set to 185 to ensure it fits within margins
        pdf.multi_cell(185, 5, clean_text(risk.get('evidence')))
        pdf.ln(2)

        # --- RECOMMENDATION BLOCK ---
        pdf.set_fill_color(240, 244, 255) # Light blue high-professional bg
        pdf.set_x(14)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(30, 58, 138)
        pdf.cell(185, 6, "  RECOMMENDATION", fill=True, border="LTR", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_x(14)
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(31, 41, 55)
        # Use a boxed multi_cell for the recommendation text
        pdf.multi_cell(185, 6, clean_text(risk.get('recommendation')), border="LBR", fill=True)
        
        pdf.ln(12) # Spacing before next risk entry

    pdf_bytes = pdf.output()
    return BytesIO(pdf_bytes)



@app.route('/generate-risk-report', methods=['POST'])
@jwt_required() # Added to ensure you have the 'uid'
def generate_report():
    uid = get_jwt_identity()
    data = request.json
    analysis_data = data.get('context', {})
    doc_id = analysis_data.get('doc_id', 'unknown')
    
    # 1. Generate the PDF bytes
    pdf_stream = create_risk_report(analysis_data)
    pdf_bytes = pdf_stream.getvalue()
    
    # 2. Store the actual PDF file in GridFS
    pdf_id = fs.put(pdf_bytes, filename=f"Risk_Report_{doc_id}.pdf")
    
    # 3. Insert the reference into your "documents" collection (Cloud Atlas)
    documents.insert_one({
        "user_id": uid,
        "title": f"Risk Report: {analysis_data.get('file_name', 'Document')}",
        "type": "risk_report",
        "doc_id_ref": doc_id,
        "created_at": datetime.utcnow(),
        "pdf_id": pdf_id  # This links to the file in GridFS
    })
    
    # 4. Return the file to the user for download
    pdf_stream.seek(0)
    return send_file(
        pdf_stream,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Risk_Report_{doc_id}.pdf"
    )
# ----------------------------------------------------
# 2. CORS ORIGIN HELPER
# ----------------------------------------------------



def is_allowed_origin(origin):
    if not origin:
        return False
    
    # List your exact production and dev URLs
    allowed_origins = [
        "https://legal-tech-frontend-02.vercel.app",
        "https://legal-tech-opal.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000"
    ]
    
    # Check for exact match or Vercel preview patterns
    if origin in allowed_origins:
        return True
    if ".vercel.app" in origin and "legal-tech" in origin:
        return True
        
    return False

# ----------------------------------------------------
# 3. CORS SETUP
# ----------------------------------------------------

CORS(app,
     supports_credentials=True,
     origins=is_allowed_origin,
     allow_headers=["Content-Type", "Authorization", "X-Requested-With", "ngrok-skip-browser-warning"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

@app.after_request
def add_headers(response):
    origin = request.headers.get('Origin')
    if origin and is_allowed_origin(origin):
        response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, ngrok-skip-browser-warning'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['ngrok-skip-browser-warning'] = 'true'
    return response

@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    resp = Response()
    origin = request.headers.get('Origin')
    if is_allowed_origin(origin):
        resp.headers['Access-Control-Allow-Origin'] = origin
        resp.headers['Access-Control-Allow-Credentials'] = 'true'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return resp, 200

# ----------------------------------------------------
# 4. DATABASE + BLUEPRINTS
# ----------------------------------------------------


client = MongoClient(MONGO_URI)
# Test the connection immediately on startup
try:
    client.admin.command('ping')
    print("✅ Connected to MongoDB Atlas!")
except Exception as e:
    print("❌ MongoDB Connection Failed:", e)
    
db = client["legal-tech"]
users = db.users
documents = db.documents
fs = GridFS(db)

# ----------------------------------------------------
# 5. AUTH ROUTES
# ----------------------------------------------------

def find_user_by_email(email):
    return users.find_one({"email": email})

@app.route("/auth/register", methods=["POST"])
def register():
    data = request.json
    email, password, name = data.get("email"), data.get("password"), data.get("name")

    if find_user_by_email(email):
        return jsonify({"msg": "User already exists"}), 400

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    users.insert_one({
        "email": email,
        "password": hashed,
        "name": name,
        "created_at": datetime.utcnow()
    })
    return jsonify({"msg": "Registered successfully"}), 201

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.json
    email, password = data.get("email"), data.get("password")

    user = find_user_by_email(email)
    if not user:
        return jsonify({"msg": "Invalid credentials"}), 401

    stored_pw = user.get("password")
    pw_bytes = stored_pw if isinstance(stored_pw, bytes) else stored_pw.encode()

    if not bcrypt.checkpw(password.encode(), pw_bytes):
        return jsonify({"msg": "Invalid credentials"}), 401

    token = create_access_token(identity=str(user["_id"]))
    refresh = create_refresh_token(identity=str(user["_id"]))

    resp = jsonify({"msg": "login ok"})
    set_access_cookies(resp, token)
    set_refresh_cookies(resp, refresh)
    return resp, 200

@app.route("/auth/me")
@jwt_required(optional=True)
def me():
    uid = get_jwt_identity()
    if not uid:
        return jsonify({"user": None}), 200

    u = users.find_one({"_id": ObjectId(uid)})
    return jsonify({"user": {
        "email": u["email"],
        "name": u.get("name", ""),
        "company": u.get("company", ""),
        "role": u.get("role", ""),
        "picture": u.get("picture", "")
    }}), 200

@app.route("/auth/logout", methods=["POST"])
def logout():
    resp = jsonify({"msg": "logout"})
    unset_jwt_cookies(resp)
    return resp, 200

# ----------------------------------------------------
# 6. PROFILE & DOCUMENT ROUTES
# ----------------------------------------------------

@app.route("/api/profile", methods=["GET"])
@jwt_required()
def get_profile():
    uid = get_jwt_identity()
    u = users.find_one({"_id": ObjectId(uid)})
    return jsonify({
        "email": u["email"],
        "name": u.get("name", ""),
        "company": u.get("company", ""),
        "role": u.get("role", ""),
        "phone": u.get("phone", ""),
        "address": u.get("address", ""),
        "bio": u.get("bio", ""),
        "picture": u.get("picture", "")
    })

@app.route("/api/profile", methods=["POST"])
@jwt_required()
def update_profile():
    uid = get_jwt_identity()
    payload = request.json
    allowed = ["name", "company", "role", "phone", "address", "bio"]
    update = {k: payload[k] for k in allowed if k in payload}

    if not update:
        return jsonify({"msg": "Nothing to update"}), 400

    users.update_one({"_id": ObjectId(uid)}, {"$set": update})
    return jsonify({"msg": "Profile updated"}), 200


@app.route("/get-template/<name>")
def get_template(name):
    valid_names = {
        "founders": "founders-agreement-template.html",
        "nda": "nda-agreement-template.html",
        "consulting-agreement": "consulting-agreement-template.html",
        "convertible-note": "convertible-note-template.html"
    }

    file_name = valid_names.get(name)
    if not file_name:
        return jsonify({"msg": "Template not recognized"}), 404

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(BASE_DIR, "templates", file_name)

    if not os.path.exists(template_path):
        return jsonify({"msg": "File not found"}), 404

    return Response(open(template_path).read(), mimetype="text/html")
    valid_names = {
        "founders": "founders-agreement-template.html",
        "nda": "nda-agreement-template.html",
        "consulting-agreement": "consulting-agreement-template.html",
        "convertible-note": "convertible-note-template.html"
    }
    file_name = valid_names.get(name)
    if not file_name:
        return jsonify({"msg": "Template not recognized"}), 404

    template_path = f"templates/{file_name}"
    if not os.path.exists(template_path):
        return jsonify({"msg": "File not found"}), 404

    return Response(open(template_path).read(), mimetype="text/html")

@app.route("/generate", methods=["POST"])
@jwt_required()
def generate_pdf():
    uid = get_jwt_identity()
    data = request.json
    doc_type = data.get("document_type")
    context = data.get("context", {})

    mapping = {
        "founders": ("founders-agreement-template.html", "Founders Agreement"),
        "nda": ("nda-agreement-template.html", "NDA Agreement"),
        "consulting-agreement": ("consulting-agreement-template.html", "Consulting Agreement"),
        "convertible-note": ("convertible-note-template.html", "Convertible Promissory Note")
    }

    if doc_type not in mapping:
        return jsonify({"msg": "Invalid type"}), 400

    file_name, title = mapping[doc_type]
    html = open(f"templates/{file_name}", "r", encoding="utf-8").read()

    def replacer(match):
        key = match.group(1).strip().lower()
        return str(context.get(key.upper(), "________________________"))

    html = re.sub(r"{{\s*([^}]+)\s*}}", replacer, html)
    pdf_bytes = HTML(string=html).write_pdf()
    pdf_id = fs.put(pdf_bytes, filename=f"{doc_type}.pdf")

    documents.insert_one({
        "user_id": uid, "title": title, "type": doc_type,
        "created_at": datetime.utcnow(), "pdf_id": pdf_id
    })

    return send_file(BytesIO(pdf_bytes), as_attachment=True, download_name=f"{doc_type}.pdf", mimetype="application/pdf")

@app.route("/api/documents", methods=["GET"])
@jwt_required()
def get_user_docs():
    uid = get_jwt_identity()
    docs = list(documents.find({"user_id": uid}))
    for d in docs:
        d["_id"] = str(d["_id"])
        d["pdf_id"] = str(d["pdf_id"])
    return jsonify(docs)

@app.route("/risk-analysis", methods=["POST"])
def risk_analysis():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        file.save(tmp.name)
        pdf_path = tmp.name

    try:
        result = run_risk_analysis(pdf_path)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)



@app.route("/redraft", methods=["POST"])
@jwt_required()
def handle_redraft():
    data = request.json
    old_html = data.get("html", "")
    user_instructions = data.get("instructions", "")

    if not old_html or not user_instructions:
        return jsonify({"msg": "Missing HTML or instructions"}), 400

    # Professional Prompt for Legal Redrafting
    prompt = f"""
    You are an expert legal counsel. Redraft the following contract HTML based on the user's instructions.
    
    USER INSTRUCTIONS: {user_instructions}
    
    ORIGINAL HTML:
    {old_html}
    
    RULES:
    1. Maintain all existing legal protections unless specifically asked to change them.
    2. Return ONLY the updated HTML. Do not include conversational text or markdown code blocks.
    3. Ensure the HTML is valid and professionally formatted.
    """

    # Use your existing SDK logic (SDK handles the response_format)
    # Note: For redrafting text, we don't necessarily need json_object format, 
    # but since your SDK function uses it, we will extract the result.
    raw_response, duration = generate_with_ollama(prompt)
    
    # If your SDK forces json_object, extract the 'html' or 'content' key
    # Otherwise, return the raw text if you've updated the SDK for general text
    try:
        data = json.loads(raw_response)
        redrafted_html = data.get("html", raw_response)
    except:
        redrafted_html = raw_response

    return jsonify({
        "redrafted_html": redrafted_html,
        "duration": duration
    }), 200

# Route to render the redrafted HTML as a professional PDF
@app.route("/redraft/render_pdf", methods=["POST"])
@jwt_required()
def render_redrafted_pdf():
    data = request.json
    html_content = data.get("html", "")
    
    if not html_content:
        return jsonify({"msg": "No HTML provided"}), 400

    # Reuse your existing WeasyPrint logic
    try:
        pdf_bytes = HTML(string=html_content).write_pdf()
        return send_file(
            BytesIO(pdf_bytes), 
            mimetype='application/pdf', 
            as_attachment=True, 
            download_name="redrafted_contract.pdf"
        )
    except Exception as e:
        return jsonify({"msg": f"PDF Error: {str(e)}"}), 500
    
    

if __name__ == "__main__":
    # Use the port assigned by Render, defaulting to 5000 if not found
    app.run(debug=True)