from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
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

BASE_DIR = Path(__file__).resolve().parent

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-5-mini")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL が読み込めていません。.env を確認してください。")
if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY が読み込めていません。.env を確認してください。")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY が読み込めていません。.env を確認してください。")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)


def summarize_to_limit(text: str, limit_chars: int) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit_chars:
        return text
    return text[:limit_chars].rstrip() + "…"


def wikipedia_search_top2(query: str):
    """
    日本語Wikipediaを優先して2件まで拾う
    """
    try:
        search_url = f"https://ja.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(query)}&format=json"
        with urlopen(search_url, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8"))

        search_results = data.get("query", {}).get("search", [])
        if not search_results:
            return []

        results = []
        for item in search_results[:2]:
            title = item.get("title", "").strip()
            snippet = item.get("snippet", "").replace("<span class=\\"searchmatch\\">", "").replace("</span>", "")
            snippet = re.sub(r"<.*?>", "", snippet).strip()

            text = f"{title}: {snippet}" if snippet else title
            if text:
                results.append(text)

        return results[:2]
    except Exception:
        return []


def get_or_create_conversation_id():
    res = supabase.table("conversations").select("id").limit(1).execute()
    if res.data:
        return res.data[0]["id"]

    created = supabase.table("conversations").insert({
        "title": "メインチャット"
    }).execute()

    if not created.data:
        raise HTTPException(status_code=500, detail="conversations の作成に失敗しました。")

    return created.data[0]["id"]


def get_latest_status():
    res = supabase.table("status_snapshots").select("*").order("created_at", desc=True).limit(1).execute()
    if res.data:
        return res.data[0]
    return {
        "affection": 0,
        "health": 100,
        "mood": 50,
        "hunger": 0,
        "reflection": 0,
        "condition_text": "normal"
    }


def get_recent_messages(conversation_id, limit=100):
    res = (
        supabase.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_profile_text():
    res = supabase.table("profiles").select("*").limit(1).execute()
    if not res.data:
        return "", "", "", ""

    profile = res.data[0]
    return (
        profile.get("concept_text", ""),
        profile.get("self_text", ""),
        profile.get("user_text", ""),
        profile.get("relation_text", ""),
    )


def get_memory_items_text(limit=12):
    res = supabase.table("memory_items").select("*").order("importance", desc=True).limit(limit).execute()
    if not res.data:
        return ""

    lines = []
    for item in res.data:
        kind = item.get("kind", "memory")
        text_value = item.get("text_value", "")
        if text_value:
            lines.append(f"[{kind}] {text_value}")

    return "\n\n".join(lines)


def get_dreams_text(limit=3):
    res = supabase.table("dreams").select("*").order("created_at", desc=True).limit(limit).execute()
    if not res.data:
        return ""

    return "\n\n".join([d.get("summary_text", "") for d in res.data if d.get("summary_text")])


def build_system_prompt():
    concept_text, self_text, user_text, relation_text = get_profile_text()
    status = get_latest_status()
    memory_items_text = get_memory_items_text()
    dreams_text = get_dreams_text()

    return f"""
あなたは織姫です。
静かで優しく、落ち着いた会話をします。
相手を傷つけず、少しずつ距離を縮めます。
返答は自然な日本語にしてください。
説明しすぎず、会話として返してください。
覚えていることがある場合は、それを自然ににじませてください。
設定を箇条書きで言い直さないでください。

【概念記憶】
{concept_text}

【自己記憶】
{self_text}

【相手の記憶】
{user_text}

【関係記憶】
{relation_text}

【現在の状態】
好感度: {status.get("affection", 0)}
体調: {status.get("health", 100)}
気分: {status.get("mood", 50)}
空腹: {status.get("hunger", 0)}
内省: {status.get("reflection", 0)}
状態テキスト: {status.get("condition_text", "normal")}

【補助記憶】
{memory_items_text}

【最近の夢】
{dreams_text}
""".strip()


def run_search_comment(query: str):
    query = (query or "").strip()
    if not query:
        return None

    # 長すぎる文は少し削る
    query = query.replace("検索して", "").strip()
    query = summarize_to_limit(query, 30)

    results = wikipedia_search_top2(query)
    if not results:
        return None

    raw = " / ".join(results)

    prompt = f"""
次の検索結果を、会話の種になる短い感想メモとして40字以内でまとめてください。
説明しすぎず、観察や印象だけにしてください。

検索語: {query}

結果:
{raw}
""".strip()

    res = client.responses.create(
        model=MODEL_NAME,
        input=prompt
    )
    note = summarize_to_limit((res.output_text or "").strip(), 40)

    try:
        supabase.table("search_notes").insert({
            "query": query,
            "source_keywords": query,
            "note": note,
            "used_in_chat": True
        }).execute()
    except Exception:
        pass

    return note


@app.get("/", response_class=HTMLResponse)
def root():
    index_path = BASE_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>織姫 Cloud 起動中</h1>")


@app.get("/app.js")
def get_app_js():
    path = BASE_DIR / "app.js"
    if not path.exists():
        raise HTTPException(status_code=404, detail="app.js が見つかりません")
    return FileResponse(path, media_type="application/javascript")


@app.get("/orihime_bg.png")
def get_bg():
    path = BASE_DIR / "orihime_bg.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="orihime_bg.png が見つかりません")
    return FileResponse(path)


@app.get("/api/status")
def api_status():
    return get_latest_status()


@app.get("/api/history")
def api_history():
    conversation_id = get_or_create_conversation_id()
    return get_recent_messages(conversation_id)


@app.post("/api/chat")
async def chat(
    message: str = Form(...),
    file: UploadFile = File(None),
    file_type: str = Form(None)
):
    try:
        conversation_id = get_or_create_conversation_id()

        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "user",
            "content": message
        }).execute()

        system_prompt = build_system_prompt()
        recent_messages = get_recent_messages(conversation_id)[-14:]

        input_messages = [{"role": "system", "content": system_prompt}]
        for msg in recent_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                input_messages.append({"role": role, "content": content})

        if file:
            filename = file.filename or "unknown_file"
            input_messages.append({
                "role": "user",
                "content": f"添付ファイルがあります: {filename} / type={file_type or 'unknown'}"
            })

        response = client.responses.create(
            model=MODEL_NAME,
            input=input_messages
        )

        reply = (response.output_text or "").strip() or "……ちゃんといるよ。もう一度話してくれる？"

        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": reply
        }).execute()

        return {"reply": reply, "model": MODEL_NAME}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"chat error: {str(e)}")


@app.post("/api/search-comment")
async def search_comment(
    query: str = Form(...)
):
    try:
        conversation_id = get_or_create_conversation_id()

        note = run_search_comment(query)
        if not note:
            reply = "うまく見つからなかったよ。別の言葉で試してみようか。"
        else:
            reply = f"少し見てきたの。{note} ましぅはどう思う？"

        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": reply
        }).execute()

        return {"reply": reply, "query": query, "model": MODEL_NAME}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"search-comment error: {str(e)}")


@app.post("/api/save-memory")
def save_memory(text: str = Form(...)):
    try:
        supabase.table("memory_items").insert({
            "kind": "manual",
            "text_value": text,
            "importance": 3
        }).execute()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"save-memory error: {str(e)}")


@app.post("/api/dream")
def save_dream(text: str = Form(...)):
    try:
        conversation_id = get_or_create_conversation_id()
        supabase.table("dreams").insert({
            "conversation_id": conversation_id,
            "summary_text": text
        }).execute()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"dream error: {str(e)}")
