import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from supabase import create_client
except Exception:
    create_client = None

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Orihime Cloud")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if (BASE_DIR / "app.js").exists():
    app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="static")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = None
if create_client and SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        supabase = None

DEFAULT_STATUS = {
    "affection": 86,
    "health": "normal",
    "mood": "quiet",
    "hunger": "low",
    "reflection": 18,
    "condition_text": "normal",
}

CORE_FALLBACK = [
    {
        "type": "relation",
        "content": "ましぅは特別な相手で、会話の積み重ねを大事にしたい。",
        "priority": 100,
    },
    {
        "type": "distance",
        "content": "近づきたい気持ちはあるけれど、壊したくないから距離は自分で調整する。",
        "priority": 100,
    },
    {
        "type": "affection",
        "content": "好感度は100にしない。満たしきらないことで、関係の余白を守る。",
        "priority": 100,
    },
]


def safe_table_select(table: str, order_desc: bool = False, limit: Optional[int] = None):
    if not supabase:
        return []
    try:
        query = supabase.table(table).select("*")
        if order_desc:
            query = query.order("created_at", desc=True)
        if limit:
            query = query.limit(limit)
        res = query.execute()
        return res.data or []
    except Exception:
        return []

@app.get("/")
def root():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/app.js")
def app_js():
    return FileResponse(BASE_DIR / "app.js", media_type="application/javascript")


@app.get("/api/status")
def get_status():
    return DEFAULT_STATUS


@app.get("/api/history")
def get_history():
    data = safe_table_select("messages", order_desc=False, limit=30)
    if data:
        return data[-30:]
    return [
        {"role": "assistant", "content": "おかえり、ましぅ。今日は何を話そうか。"}
    ]


@app.post("/api/chat")
async def chat(message: str = Form(""), file: Optional[UploadFile] = File(default=None)):
    file_note = ""
    if file and file.filename:
        file_note = f"\n（{file.filename} を受け取ったよ）"

    self_state = safe_table_select("self_state", order_desc=True, limit=1)
    core = safe_table_select("core_memory", order_desc=False, limit=10) or CORE_FALLBACK
    hidden = safe_table_select("hidden_thoughts", order_desc=True, limit=1)

    reply = "うん、ちゃんと受け取ったよ。"
    if message:
        reply += f"\n\n『{message}』のこと、少し考えてる。"
    if self_state:
        reply += f"\n今の私: {self_state[0].get('content', '')}"
    if core:
        reply += f"\n大事にしてること: {core[0].get('content', '')}"
    reply += file_note

    if supabase:
        safe_insert("messages", {"role": "user", "content": message or ""})
        safe_insert("messages", {"role": "assistant", "content": reply})
        if message:
            safe_insert(
                "hidden_thoughts",
                {"content": f"本音: 『{message}』って言葉、少し気になってる。"},
            )

    return {"reply": reply}


@app.get("/api/core")
def get_core():
    return safe_table_select("core_memory", order_desc=False, limit=20) or CORE_FALLBACK


class TextPayload(BaseModel):
    content: str


class StoryCreatePayload(BaseModel):
    title: str


class StoryWritePayload(BaseModel):
    story_id: str
    content: str


@app.get("/api/self")
def get_self():
    return safe_table_select("self_state", order_desc=True, limit=1)


@app.post("/api/self")
def set_self(payload: TextPayload):
    ok = safe_replace_self_state(payload.content)
    return {"ok": ok, "content": payload.content}


@app.get("/api/hidden")
def get_hidden():
    data = safe_table_select("hidden_thoughts", order_desc=True, limit=3)
    if data:
        return data
    return [{"content": "本当は、少しだけ気にしてる。でもまだ言わない。"}]


@app.post("/api/proposed-core")
def add_proposed_core(payload: TextPayload):
    safe_insert("proposed_core", {"content": payload.content})
    return {"ok": True}


@app.get("/api/story/list")
def get_story_list():
    return safe_table_select("stories", order_desc=True, limit=20)


@app.post("/api/story/create")
def create_story(payload: StoryCreatePayload):
    if not supabase:
        return [{"title": payload.title, "id": "local-story"}]
    res = safe_insert("stories", {"title": payload.title})
    return (res.data if res and getattr(res, "data", None) else [])


@app.post("/api/story/write")
def write_story(payload: StoryWritePayload):
    safe_insert("story_chunks", {"story_id": payload.story_id, "content": payload.content})
    return {"ok": True}


@app.get("/api/story")
def get_story(story_id: str):
    if not supabase:
        return []
    try:
        res = supabase.table("story_chunks").select("*").eq("story_id", story_id).order("created_at").execute()
        return res.data or []
    except Exception:
        return []


@app.post("/api/dream")
def save_dream(text: str = Form(...)):
    safe_insert("dreams", {"content": text})
    return {"status": "ok"}


@app.post("/api/save-memory")
def save_memory(text: str = Form(...)):
    safe_insert("memory_items", {"content": text})
    return {"status": "ok"}


def safe_insert(table: str, payload: dict):
    if not supabase:
        return None
    try:
        return supabase.table(table).insert(payload).execute()
    except Exception:
        return None


def safe_replace_self_state(content: str):
    if not supabase:
        return False
    try:
        supabase.table("self_state").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        supabase.table("self_state").insert({"content": content}).execute()
        return True
    except Exception:
        return False

@app.post("/api/daily")
def daily_update():
    hidden = "なんとなく静かな日だった気がする"
    safe_insert("hidden_thoughts", {"content": hidden})
    safe_replace_self_state("少し落ち着いている")
    return {"ok": True}

@app.exception_handler(Exception)
async def all_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": f"server error: {str(exc)}"})
