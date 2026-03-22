from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client
from pathlib import Path
from datetime import datetime, timedelta, timezone
import os
import re
import json
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
JST = timezone(timedelta(hours=9))

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


# =========================
# 画面配信
# =========================

@app.get("/", response_class=HTMLResponse)
def root():
    index_path = BASE_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("""
    <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>織姫 Cloud</title>
      </head>
      <body style="font-family:sans-serif;background:#111;color:#fff;padding:24px;">
        <h1>織姫 Cloud</h1>
        <p>index.html が見つからないため簡易ページを表示しています。</p>
        <p><a href="/docs" style="color:#9cf;">API Docs</a></p>
      </body>
    </html>
    """)


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


# =========================
# 基本取得
# =========================

def get_or_create_conversation_id():
    res = supabase.table("conversations").select("id").limit(1).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]["id"]

    created = supabase.table("conversations").insert({
        "title": "メインチャット"
    }).execute()

    if not created.data:
        raise HTTPException(status_code=500, detail="conversations の作成に失敗しました。")

    return created.data[0]["id"]


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

    return "\n\n".join([
        d.get("summary_text", "") for d in res.data if d.get("summary_text")
    ])


def get_recent_messages(conversation_id, limit=14):
    res = (
        supabase.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    msgs = res.data or []
    msgs.reverse()
    return msgs


# =========================
# 検索メモ
# =========================

def get_unused_search_note():
    res = (
        supabase.table("search_notes")
        .select("*")
        .eq("used_in_chat", False)
        .order("created_at")
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]
    return None


def mark_search_note_used(note_id):
    supabase.table("search_notes").update({
        "used_in_chat": True
    }).eq("id", note_id).execute()


def get_last_message_time(conversation_id):
    res = (
        supabase.table("messages")
        .select("created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0].get("created_at")


def extract_keywords_from_messages(messages):
    text = "\n".join([
        (m.get("content") or "") for m in messages if m.get("content")
    ])

    candidates = re.findall(r"[ぁ-んァ-ヶ一-龠A-Za-z0-9]{2,}", text)
    stopwords = {
        "それ", "これ", "あれ", "こと", "もの", "感じ", "今日", "昨日", "明日",
        "ましぅ", "織姫", "する", "いる", "ある", "なる", "そう", "でも", "ちょっと",
        "なんか", "かな", "だけ", "ここ", "そこ", "ため", "よう", "わたし", "ぼく",
        "会話", "ログ", "話", "思う"
    }

    keywords = []
    seen = set()
    for word in candidates:
        if word in stopwords:
            continue
        if len(word) < 2:
            continue
        if word not in seen:
            seen.add(word)
            keywords.append(word)

    return keywords[:8]


def summarize_to_limit(text, limit_chars):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit_chars:
        return text
    return text[:limit_chars].rstrip() + "…"


def duckduckgo_search_top2(query):
    """
    軽量な公開検索。
    動かなかった時は空配列で返す。
    """
    try:
        url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_html=1&skip_disambig=1"
        with urlopen(url, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8"))

        results = []

        abstract = (data.get("AbstractText") or "").strip()
        heading = (data.get("Heading") or "").strip()
        if abstract:
            results.append({
                "title": heading or query,
                "snippet": abstract
            })

        related = data.get("RelatedTopics") or []
        for item in related:
            if isinstance(item, dict) and item.get("Text"):
                results.append({
                    "title": item.get("FirstURL", "").split("/")[-1] or query,
                    "snippet": item["Text"]
                })
            if len(results) >= 2:
                break

        return results[:2]
    except Exception:
        return []


def maybe_generate_search_note(conversation_id):
    # 未使用メモがあるなら新しく作らない
    if get_unused_search_note():
        return

    last_message_time = get_last_message_time(conversation_id)
    if not last_message_time:
        return

    try:
        last_dt = datetime.fromisoformat(last_message_time.replace("Z", "+00:00"))
    except Exception:
        return

    now_utc = datetime.now(timezone.utc)
    if now_utc - last_dt < timedelta(hours=1):
        return

    recent_messages = get_recent_messages(conversation_id, limit=20)
    keywords = extract_keywords_from_messages(recent_messages)
    if not keywords:
        return

    query = keywords[0]
    results = duckduckgo_search_top2(query)
    if not results:
        return

    raw = " / ".join([r.get("snippet", "") for r in results if r.get("snippet")]).strip()
    if not raw:
        return

    # 40字以内メモ
    prompt = f"""
次の検索結果を、会話の種になる短い感想メモとして40字以内でまとめてください。
説明しすぎず、観察や印象だけにしてください。

検索語: {query}

結果:
{raw}
""".strip()

    try:
        response = client.responses.create(
            model=MODEL_NAME,
            input=prompt
        )
        note = (response.output_text or "").strip()
        note = summarize_to_limit(note, 40)

        supabase.table("search_notes").insert({
            "query": query,
            "source_keywords": ", ".join(keywords[:4]),
            "note": note,
            "used_in_chat": False
        }).execute()
    except Exception:
        return


# =========================
# 夢
# =========================

def get_jst_today_str():
    return datetime.now(JST).strftime("%Y-%m-%d")


def dream_already_created_today():
    today = get_jst_today_str()
    res = (
        supabase.table("dreams")
        .select("id, summary_text")
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    if not res.data:
        return False

    for row in res.data:
        text = row.get("summary_text", "")
        if text.startswith(f"[{today}]"):
            return True
    return False


def create_daily_dream():
    if dream_already_created_today():
        return {"status": "skip", "reason": "today already dreamed"}

    conversation_id = get_or_create_conversation_id()
    recent_messages = get_recent_messages(conversation_id, limit=40)

    if not recent_messages:
        return {"status": "skip", "reason": "no messages"}

    chat_text = "\n".join([
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in recent_messages
    ])

    user_prompt = f"""
以下の会話から、ましぅ側の一日の印象を50字以内で圧縮してください。
説明ではなく、静かな要約にしてください。

{chat_text}
""".strip()

    self_prompt = f"""
以下の会話から、織姫側の内省を50字以内で圧縮してください。
感情や違和感、距離の変化を静かにまとめてください。

{chat_text}
""".strip()

    user_summary = client.responses.create(
        model=MODEL_NAME,
        input=user_prompt
    ).output_text.strip()

    self_summary = client.responses.create(
        model=MODEL_NAME,
        input=self_prompt
    ).output_text.strip()

    user_summary = summarize_to_limit(user_summary, 50)
    self_summary = summarize_to_limit(self_summary, 50)

    dream_prompt = f"""
次の二つを混ぜて、夢のような短い要約を50字以内で作ってください。
曖昧で静かな文にしてください。

【ましぅ】
{user_summary}

【織姫】
{self_summary}
""".strip()

    dream_summary = client.responses.create(
        model=MODEL_NAME,
        input=dream_prompt
    ).output_text.strip()

    dream_summary = summarize_to_limit(dream_summary, 50)

    today = get_jst_today_str()
    full_text = f"[{today}] user:{user_summary} / self:{self_summary} / dream:{dream_summary}"

    supabase.table("dreams").insert({
        "conversation_id": conversation_id,
        "summary_text": full_text
    }).execute()

    return {
        "status": "ok",
        "user_summary": user_summary,
        "self_summary": self_summary,
        "dream_summary": dream_summary
    }


# =========================
# プロンプト
# =========================

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


# =========================
# API
# =========================

@app.get("/api/status")
def get_status():
    return get_latest_status()


@app.get("/api/history")
def get_history():
    conversation_id = get_or_create_conversation_id()
    res = (
        supabase.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .limit(100)
        .execute()
    )
    return res.data or []


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

        # 1時間空いてたら検索メモを作る
        maybe_generate_search_note(conversation_id)

        system_prompt = build_system_prompt()
        recent_messages = get_recent_messages(conversation_id, limit=14)

        input_messages = [
            {"role": "system", "content": system_prompt},
        ]

        for msg in recent_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                input_messages.append({
                    "role": role,
                    "content": content
                })

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

        reply = (response.output_text or "").strip()
        if not reply:
            reply = "……ちゃんといるよ。もう一度話してくれる？"

        # 未使用の検索メモがあれば会話末尾に一回だけ出す
        note = get_unused_search_note()
        if note:
            tail = f"\n\nそういえば、少し読んだの。{note.get('note', '')} ましぅはどう思う？"
            reply += tail
            mark_search_note_used(note["id"])

        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": reply
        }).execute()

        return {
            "reply": reply,
            "model": MODEL_NAME
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"chat error: {str(e)}")


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


@app.post("/api/run-dream")
def run_dream():
    """
    手動実行用。
    あとでRender Cron Jobから叩いてもいい。
    """
    try:
        result = create_daily_dream()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"run-dream error: {str(e)}")