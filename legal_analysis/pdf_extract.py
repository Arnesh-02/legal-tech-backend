# pdf_extract.py
import pdfplumber
import re
from tika import parser

def extract_text_pdfplumber(path):
    texts = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texts.append(t)
    except Exception:
        return ""
    return "\n\n".join(texts).strip()

def extract_text_tika(path):
    try:
        raw = parser.from_file(path)
        return raw.get("content") or ""
    except Exception:
        return ""

# IMPORTANT: This is now renamed to match what the pipeline expects
def extract_text_from_pdf(path):
    text = extract_text_pdfplumber(path)

    # fallback to Tika if plumber returns too little
    if len(text.strip()) < 200:
        text = extract_text_tika(path)

    # clean up line breaks
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)

    return text.strip()
