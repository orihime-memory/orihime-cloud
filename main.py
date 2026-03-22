from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client
import os

load_dotenv()

app = FastAPI()

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

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL が読み込めていません。.env を確認してください。")
if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY が読み込めていません。.env を確認してください。")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY が読み込めていません。.env を確認してください。")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)


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
    return "\n\n".join([d.get("summary_text", "") for d in res.data if d.get("summary_text")])


def get_recent_messages(conversation_id, limit=12):
    res = (
        supabase.table("messages")
        .select("role, content")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    msgs = res.data or []
    msgs.reverse()
    return msgs


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
覚えていることがある場合は、それを自然に会話へにじませてください。
設定を機械的に箇条書きで言い直さないでください。

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

【夢・日記】
{dreams_text}
""".strip()


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

        system_prompt = build_system_prompt()
        recent_messages = get_recent_messages(conversation_id, limit=12)

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

        response = client.responses.create(
            model=MODEL_NAME,
            input=input_messages
        )

        reply = response.output_text.strip()

        if not reply:
            reply = "……ちゃんといるよ。もう一度話してくれる？"

        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": reply
        }).execute()

        return {"reply": reply, "model": MODEL_NAME}

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