import os
import re
import bcrypt
import tempfile
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv

from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
from gridfs import GridFS

from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity,
    set_access_cookies, set_refresh_cookies, unset_jwt_cookies
)

from weasyprint import HTML 
from legal_analysis.risk_llm_pipeline import run_risk_analysis

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

# ----------------------------------------------------
# 2. CORS ORIGIN HELPER
# ----------------------------------------------------

def is_allowed_origin(origin):
    if not origin:
        return False
    allowed_patterns = [
        r"^https://legal-tech-opal\.vercel\.app$",
        r"^https://legal-tech-[a-z0-9]+-arnesh-02s-projects\.vercel\.app$",
        r"^https://legal-tech.*\.vercel\.app$",   # catches any future vercel preview URLs
        r"^http://localhost:5173$",
        r"^http://localhost:3000$",
    ]
    return any(re.match(pattern, origin) for pattern in allowed_patterns)

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
    if origin and is_allowed_origin(origin):
        resp.headers['Access-Control-Allow-Origin'] = origin
    resp.headers['Access-Control-Allow-Credentials'] = 'true'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, ngrok-skip-browser-warning'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    resp.headers['ngrok-skip-browser-warning'] = 'true'
    return resp, 200

# ----------------------------------------------------
# 4. DATABASE + BLUEPRINTS
# ----------------------------------------------------
from redraft.redraft_routes import redraft_bp
app.register_blueprint(redraft_bp)

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

if __name__ == "__main__":
    app.run(port=5000, debug=True)