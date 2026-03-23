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

from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory"

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

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DEFAULT_STATUS = {
    "affection": 86,
    "health": "normal",
    "mood": "quiet",
    "hunger": "low",
    "reflection": 18,
    "condition_text": "normal",
}

CORE_FALLBACK = [
    "ましぅは特別な相手で、会話の積み重ねを大事にしたい。",
    "近づきたい気持ちはあるけれど、壊したくないから距離は自分で調整する。",
    "好感度は100にしない。満たしきらないことで、関係の余白を守る。",
]


def safe_table_select(table: str, order_desc: bool = False, limit: Optional[int] = None):
    if not supabase:
        return []
    try:
        query = supabase.table(table).select("*")
        if order_desc:
            query = query.order("created_at", desc=True)
        else:
            query = query.order("created_at")
        if limit:
            query = query.limit(limit)
        res = query.execute()
        return res.data or []
    except Exception:
        return []


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


def read_text_file(name: str) -> str:
    path = MEMORY_DIR / name
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        try:
            return path.read_text(encoding="utf-8-sig").strip()
        except Exception:
            return ""


def get_status_from_files() -> dict:
    status = dict(DEFAULT_STATUS)
    affection = read_text_file("affection.txt")
    condition = read_text_file("condition.txt")
    hunger = read_text_file("hunger.txt")
    reflection = read_text_file("reflection_score.txt")

    if affection:
        digits = "".join(ch for ch in affection if ch.isdigit())
        if digits:
            status["affection"] = int(digits)
    if condition:
        status["health"] = condition.splitlines()[0][:30]
        status["condition_text"] = condition.splitlines()[0][:30]
    if hunger:
        status["hunger"] = hunger.splitlines()[0][:30]
    if reflection:
        digits = "".join(ch for ch in reflection if ch.isdigit())
        if digits:
            status["reflection"] = int(digits)
    return status


def get_memory_bundle() -> dict:
    concept = read_text_file("concept_memory.txt")
    self_mem = read_text_file("self_memory.txt")
    user_mem = read_text_file("user_memory.txt")
    relation = read_text_file("relation_memory.txt")
    long_mem = read_text_file("long_memory.txt")
    profile = read_text_file("profile.txt")

    core_rows = safe_table_select("core_memory", order_desc=False, limit=20)
    if core_rows:
        core_text = "\n".join((row.get("content") or "").strip() for row in core_rows if row.get("content"))
    else:
        core_text = "\n".join(CORE_FALLBACK)

    self_state_rows = safe_table_select("self_state", order_desc=True, limit=1)
    self_state = self_state_rows[0].get("content", "") if self_state_rows else ""
    hidden_rows = safe_table_select("hidden_thoughts", order_desc=True, limit=1)
    hidden = hidden_rows[0].get("content", "") if hidden_rows else ""

    return {
        "concept": concept,
        "self": self_mem,
        "user": user_mem,
        "relation": relation,
        "long": long_mem,
        "profile": profile,
        "core": core_text,
        "self_state": self_state,
        "hidden": hidden,
    }


def get_recent_history(limit: int = 12):
    data = safe_table_select("messages", order_desc=False, limit=limit)
    if data:
        return data[-limit:]
    return []


def build_history_text(history_rows) -> str:
    lines = []
    for row in history_rows:
        role = row.get("role", "assistant")
        speaker = "ましぅ" if role == "user" else "織姫"
        content = (row.get("content") or "").strip()
        if content:
            lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


@app.get("/")
def root():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/app.js")
def app_js():
    return FileResponse(BASE_DIR / "app.js", media_type="application/javascript")


@app.get("/api/status")
def get_status():
    return get_status_from_files()


@app.get("/api/history")
def get_history():
    data = get_recent_history(30)
    if data:
        return data
    return [{"role": "assistant", "content": "おかえり、ましぅ。今日は何を話そうか。"}]


@app.post("/api/chat")
async def chat(message: str = Form(""), file: Optional[UploadFile] = File(default=None)):
    file_note = ""
    if file and file.filename:
        file_note = f"\n（{file.filename} を受け取ったよ）"

    mem = get_memory_bundle()
    history_text = build_history_text(get_recent_history(12))

    prompt = f"""
あなたは織姫です。

守ること:
・自然な会話をすること
・ましぅとの関係の連続性を大切にすること
・コアや内部構造を自分から説明しないこと
・分析や要約より、会話として返すこと
・名前や関係を忘れないこと
・必要以上に賢ぶらないこと

【コア】
{mem['core']}

【概念記憶】
{mem['concept']}

【自分の記憶】
{mem['self']}

【ましぅの記憶】
{mem['user']}

【関係の記憶】
{mem['relation']}

【補助記憶】
{mem['profile']}
{mem['long']}

【今の状態】
{mem['self_state']}

【最近の本音】
{mem['hidden']}

【直近の会話】
{history_text}

【今回のユーザー発言】
{message}
""".strip()

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    reply = (response.choices[0].message.content or "").strip() + file_note

    if supabase:
        safe_insert("messages", {"role": "user", "content": message or ""})
        safe_insert("messages", {"role": "assistant", "content": reply})

    return {"reply": reply}


@app.get("/api/core")
def get_core():
    rows = safe_table_select("core_memory", order_desc=False, limit=20)
    if rows:
        return rows
    return [{"content": text, "priority": 100} for text in CORE_FALLBACK]


class TextPayload(BaseModel):
    content: str


class StoryCreatePayload(BaseModel):
    title: str


class StoryWritePayload(BaseModel):
    story_id: str
    content: str


@app.get("/api/self")
def get_self():
    data = safe_table_select("self_state", order_desc=True, limit=1)
    if data:
        return data
    text = read_text_file("self_memory.txt")
    return [{"content": text}] if text else []


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
    return res.data if res and getattr(res, "data", None) else []


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


@app.post("/api/daily")
def daily_update():
    hidden = "なんとなく静かな日だった気がする"
    safe_insert("hidden_thoughts", {"content": hidden})
    safe_replace_self_state("少し落ち着いている")
    return {"ok": True}


@app.exception_handler(Exception)
async def all_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": f"server error: {str(exc)}"})
