
# ===== OrIhime Cloud main.py (Search trigger version) =====

from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client
from pathlib import Path
import os
import json
import re
from urllib.request import urlopen
from urllib.parse import quote

load_dotenv()

app = FastAPI(title="織姫 Cloud")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-5-mini")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# 検索機能（トリガー式）
# =========================

def summarize_to_limit(text, limit_chars):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit_chars:
        return text
    return text[:limit_chars] + "…"

def duckduckgo_search_top2(query):
    try:
        url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_html=1"
        with urlopen(url) as res:
            data = json.loads(res.read().decode("utf-8"))

        results = []
        if data.get("AbstractText"):
            results.append(data["AbstractText"])

        for r in data.get("RelatedTopics", []):
            if isinstance(r, dict) and r.get("Text"):
                results.append(r["Text"])
            if len(results) >= 2:
                break

        return results[:2]
    except:
        return []

def detect_search_query(message: str):
    if "検索して" not in message:
        return None
    return message.replace("検索して", "").strip()

def run_search(message):
    query = detect_search_query(message)
    if not query:
        return None

    results = duckduckgo_search_top2(query)
    if not results:
        return None

    raw = " / ".join(results)

    prompt = f"""
以下を40文字以内で短くまとめてください。

{raw}
"""

    res = client.responses.create(
        model=MODEL_NAME,
        input=prompt
    )

    note = summarize_to_limit(res.output_text.strip(), 40)

    return note

# =========================
# ルート
# =========================

@app.get("/", response_class=HTMLResponse)
def root():
    return "<h1>織姫 Cloud 起動中</h1>"

# =========================
# チャット
# =========================

@app.post("/api/chat")
async def chat(message: str = Form(...)):
    try:
        res = client.responses.create(
            model=MODEL_NAME,
            input=message
        )

        reply = res.output_text.strip()

        note = run_search(message)
        if note:
            reply += f"\n\nそういえば少し見てきたの。{note}"

        return {"reply": reply}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
