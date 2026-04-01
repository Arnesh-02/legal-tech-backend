import os
import requests

def call_llm(model: str, prompt: str) -> str:
    # Use 'open-mistral-7b' for the free/cheap tier
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
    url = "https://api.mistral.ai/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}"
    }

    payload = {
        "model": "open-mistral-7b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    }

    try:
        res = requests.post(url, json=payload, timeout=60)
        res.raise_for_status()
        data = res.json()
        return data['choices'][0]['message']['content'].strip()
    except Exception as e:
        print("Mistral API Error:", e)
        return f"Error calling Mistral: {str(e)}"