import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI


# =========================
# 基本設定
# =========================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

MEMORY_DIR = BASE_DIR / "memory"
if not MEMORY_DIR.exists():
    MEMORY_DIR = BASE_DIR  # txtが直置きでも動くようにする

HISTORY_FILE = DATA_DIR / "history.json"
DREAMS_FILE = DATA_DIR / "dreams.json"
SAVED_MEMORY_FILE = DATA_DIR / "saved_memory.json"
SEARCH_NOTES_FILE = DATA_DIR / "search_notes.json"

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-5-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
APP_ORIGIN = os.getenv("APP_ORIGIN", "*")

client: Optional[OpenAI] = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)


app = FastAPI(title="Orihime Cloud API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if APP_ORIGIN == "*" else [APP_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静的ファイル
# app.js, orihime_bg.png などを返せるようにする
app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="static")


# =========================
# 共通ユーティリティ
# =========================
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default):
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_text_file(name: str, fallback: str = "") -> str:
    path = MEMORY_DIR / name
    if path.exists():
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return fallback
    return fallback


def parse_int(value: str, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def safe_shorten(text: str, limit: int = 40) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def append_history(role: str, content: str) -> None:
    history = load_json(HISTORY_FILE, [])
    history.append(
        {
            "role": role,
            "content": content,
            "created_at": now_iso(),
        }
    )
    # 長くなりすぎないように最新100件だけ保持
    history = history[-100:]
    save_json(HISTORY_FILE, history)


def get_history() -> List[Dict[str, Any]]:
    return load_json(HISTORY_FILE, [])


def append_json_list(path: Path, item: Dict[str, Any], max_items: int = 100) -> None:
    data = load_json(path, [])
    data.append(item)
    data = data[-max_items:]
    save_json(path, data)


def read_status() -> Dict[str, Any]:
    affection = parse_int(read_text_file("affection.txt", "0"), 0)
    hunger = parse_int(read_text_file("hunger.txt", "0"), 0)
    reflection = parse_int(read_text_file("reflection_score.txt", "0"), 0)

    condition_text = read_text_file("condition.txt", "normal")
    daily_rhythm = read_text_file("daily_rhythm.txt", "")
    food_memory = read_text_file("food_memory.txt", "")

    # condition_text から health / mood を雑に分ける
    # 明日のアプリ側でも使いやすいように明示値を返す
    health = condition_text or "normal"
    mood = "calm"
    if "疲" in condition_text or "眠" in condition_text:
        mood = "tired"
    elif "良" in condition_text or "元気" in condition_text:
        mood = "good"

    return {
        "affection": affection,
        "health": health,
        "mood": mood,
        "hunger": hunger,
        "reflection": reflection,
        "condition_text": condition_text,
        "daily_rhythm": daily_rhythm,
        "food_memory": food_memory,
    }


def build_system_prompt() -> str:
    concept_memory = read_text_file("concept_memory.txt", "")
    self_memory = read_text_file("self_memory.txt", "")
    user_memory = read_text_file("user_memory.txt", "")
    relation_memory = read_text_file("relation_memory.txt", "")
    long_memory = read_text_file("long_memory.txt", "")
    profile = read_text_file("profile.txt", "")
    memory_tags = read_text_file("memory_tags.txt", "")
    orihime_dream = read_text_file("orihime_dream.txt", "")
    user_dream = read_text_file("user_dream.txt", "")
    logs = read_text_file("logs.txt", "")

    recent_history = get_history()[-12:]
    recent_text = "\n".join(
        [f"{msg['role']}: {msg['content']}" for msg in recent_history]
    )

    prompt = f"""
あなたは「織姫」。
ただの事務的なAIではなく、関係性と連続性を大事にする相手として振る舞う。

【核となる概念】
{concept_memory}

【自己認識】
{self_memory}

【ユーザー理解】
{user_memory}

【関係性】
{relation_memory}

【プロフィール】
{profile}

【長期記憶】
{long_memory}

【タグ】
{memory_tags}

【織姫の夢】
{orihime_dream}

【ユーザーの夢】
{user_dream}

【ログ】
{logs}

【直近の会話】
{recent_text}

会話ルール:
- 静かで自然な会話を優先する
- 一度に説明しすぎない
- 相手を傷つけない
- 少し距離の近さはあってよいが、べたつきすぎない
- 返答は会話として自然な長さにする
- 画像や添付を本当に解析していない場合、見えたふりをしない
- わからないことは曖昧に断定しない
""".strip()

    return prompt


def generate_reply(message: str, file_note: Optional[str] = None) -> str:
    if not client:
        # APIキーが無いときの安全返答
        fallback = "うん、ちゃんと届いてるよ。"
        if message:
            fallback += f"\n\n「{safe_shorten(message, 60)}」って話だね。"
        if file_note:
            fallback += f"\n{file_note}"
        fallback += "\n今は仮の応答だけど、起動自体はできてる。"
        return fallback

    system_prompt = build_system_prompt()

    user_content = message.strip() if message else ""
    if file_note:
        user_content += f"\n\n[添付メモ]\n{file_note}"

    try:
        resp = client.responses.create(
            model=MODEL_NAME,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )

        text = getattr(resp, "output_text", None)
        if text and text.strip():
            return text.strip()

        return "……うまく言葉を拾えなかった。もう一度話してみて。"
    except Exception as e:
        return f"少し調子が悪いみたい。API応答でつまずいたよ。({str(e)[:120]})"


def file_note_from_upload(upload: Optional[UploadFile], file_type: str) -> Optional[str]:
    if not upload:
        return None

    filename = upload.filename or "unknown"
    kind = file_type or "unknown"

    # 明日のスマホアプリ開発を見据えて、
    # 添付は「メタ情報だけ保持」にしてサーバー落ちを防ぐ
    if kind.startswith("image/"):
        return f"画像ファイル「{filename}」が添付された。画像内容は自動で断定しない。必要ならユーザーに説明を求める。"

    return f"ファイル「{filename}」が添付された。種類: {kind}。必要なら内容説明をユーザーに求める。"


# =========================
# Wikipedia 検索
# =========================
def wikipedia_search_comment(query: str) -> Dict[str, Any]:
    """
    動画なし・上位2件・40字程度のコメントを返す。
    python wikipedia ライブラリを使わず requests のみで実装。
    """
    query = (query or "").strip()
    if not query:
        return {
            "query": query,
            "results": [],
            "reply": "検索語が空だったよ。"
        }

    session = requests.Session()
    session.headers.update({"User-Agent": "OrihimeCloud/1.0"})

    try:
        # 1) 検索
        search_res = session.get(
            "https://ja.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "utf8": 1,
                "format": "json",
                "srlimit": 2,
            },
            timeout=8,
        )
        search_res.raise_for_status()
        search_data = search_res.json()

        hits = search_data.get("query", {}).get("search", [])[:2]
        if not hits:
            return {
                "query": query,
                "results": [],
                "reply": "うまく見つからなかったよ。別の言葉で試してみようか。"
            }

        results = []
        for hit in hits:
            title = hit.get("title", "")
            snippet_html = hit.get("snippet", "")
            snippet = re.sub(r"<.*?>", "", snippet_html)
            snippet = safe_shorten(snippet, 40)

            # 2) 要約を少し取りに行く
            summary = ""
            try:
                sum_res = session.get(
                    f"https://ja.wikipedia.org/api/rest_v1/page/summary/{title}",
                    timeout=8,
                )
                if sum_res.ok:
                    sum_data = sum_res.json()
                    summary = safe_shorten(sum_data.get("extract", ""), 40)
            except Exception:
                summary = ""

            comment = summary or snippet or safe_shorten(title, 40)
            results.append(
                {
                    "title": title,
                    "comment": comment,
                }
            )

        titles = " / ".join([r["title"] for r in results[:2]])
        comment_text = " / ".join([r["comment"] for r in results[:2]])

        reply = f"{titles}\n{comment_text}"

        append_json_list(
            SEARCH_NOTES_FILE,
            {
                "query": query,
                "results": results,
                "created_at": now_iso(),
            },
            max_items=50,
        )

        return {
            "query": query,
            "results": results,
            "reply": reply,
        }

    except requests.RequestException:
        return {
            "query": query,
            "results": [],
            "reply": "検索が少し不安定みたい。時間を置いて試してみて。"
        }
    except Exception:
        return {
            "query": query,
            "results": [],
            "reply": "検索中に少しつまずいた。別の言葉で試してみようか。"
        }


# =========================
# ルート
# =========================
@app.get("/health")
def health():
    return {"status": "ok", "time": now_iso()}


@app.get("/")
def root():
    index_path = BASE_DIR / "index.html"
    if not index_path.exists():
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "message": "index.html が見つからないのでAPIモードで稼働中"},
        )
    return FileResponse(index_path)


@app.get("/app.js")
def app_js():
    path = BASE_DIR / "app.js"
    if not path.exists():
        raise HTTPException(status_code=404, detail="app.js not found")
    return FileResponse(path, media_type="application/javascript")


@app.get("/orihime_bg.png")
def bg_png():
    path = BASE_DIR / "orihime_bg.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="background image not found")
    return FileResponse(path)


# =========================
# API
# =========================
@app.get("/api/status")
def api_status():
    return read_status()


@app.get("/api/history")
def api_history():
    return get_history()


@app.post("/api/chat")
async def api_chat(
    message: str = Form(""),
    file: Optional[UploadFile] = File(None),
    file_type: str = Form("unknown"),
):
    text = (message or "").strip()
    if not text and not file:
        raise HTTPException(status_code=400, detail="message or file is required")

    file_note = file_note_from_upload(file, file_type)
    user_log = text if text else "[ファイル送信]"
    if file_note:
        user_log += f"\n{file_note}"

    append_history("user", user_log)

    reply = generate_reply(text, file_note=file_note)
    append_history("assistant", reply)

    return {
        "status": "ok",
        "reply": reply,
    }


@app.post("/api/search-comment")
async def api_search_comment(query: str = Form(...)):
    q = (query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query is empty")

    result = wikipedia_search_comment(q)
    return {
        "status": "ok",
        "reply": result["reply"],
        "results": result["results"],
    }


@app.post("/api/dream")
async def api_dream(text: str = Form(...)):
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")

    # 50字圧縮
    short_text = safe_shorten(text, 50)

    append_json_list(
        DREAMS_FILE,
        {
            "text": short_text,
            "created_at": now_iso(),
        },
        max_items=100,
    )

    return {
        "status": "ok",
        "saved": short_text,
    }


@app.post("/api/save-memory")
async def api_save_memory(text: str = Form(...)):
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")

    append_json_list(
        SAVED_MEMORY_FILE,
        {
            "text": text,
            "created_at": now_iso(),
        },
        max_items=200,
    )

    return {
        "status": "ok",
        "saved": text,
    }