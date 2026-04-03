import base64
import json
import mimetypes
import os
import random
import re
from datetime import datetime
from pathlib import Path

import requests
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from openai import OpenAI

try:
    from docx import Document
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory"
UPLOADS_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
CHAPTERS_DIR = MEMORY_DIR / "chapters"
ARCHIVE_DIR = MEMORY_DIR / "archive"
GENERATED_AUDIO_DIR = STATIC_DIR / "generated_audio"

PROFILE_FILE = MEMORY_DIR / "profile.txt"
CORE_FILE = MEMORY_DIR / "core_memory.txt"
LONG_MEMORY_FILE = MEMORY_DIR / "long_memory.txt"
LOG_FILE = MEMORY_DIR / "logs.txt"
AFFECTION_FILE = MEMORY_DIR / "affection.txt"
MEMORY_TAGS_FILE = MEMORY_DIR / "memory_tags.txt"
SELF_MEMORY_FILE = MEMORY_DIR / "self_memory.txt"
SELF_STATE_FILE = MEMORY_DIR / "self_state.txt"
HIDDEN_FILE = MEMORY_DIR / "hidden_thoughts.txt"
RELATION_FILE = MEMORY_DIR / "relation_memory.txt"
EDITABLE_SCOPE_FILE = MEMORY_DIR / "editable_scope.txt"
PLOT_FILE = MEMORY_DIR / "story_plot.json"
DOCUMENT_DIGESTS_FILE = MEMORY_DIR / "document_digests.txt"
PLOT_DISCUSSION_FILE = MEMORY_DIR / "plot_discussion.txt"

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
TAG_MODEL = os.getenv("OPENAI_TAG_MODEL", OPENAI_MODEL)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

STYLE_BERT_VITS2_URL = os.getenv("STYLE_BERT_VITS2_URL", "http://127.0.0.1:5000/voice").strip()
STYLE_BERT_VITS2_MODEL_ID = os.getenv("STYLE_BERT_VITS2_MODEL_ID", "0").strip()
STYLE_BERT_VITS2_SPEAKER_ID = os.getenv("STYLE_BERT_VITS2_SPEAKER_ID", "0").strip()
STYLE_BERT_VITS2_STYLE = os.getenv("STYLE_BERT_VITS2_STYLE", "Neutral").strip()
STYLE_BERT_VITS2_STYLE_WEIGHT = os.getenv("STYLE_BERT_VITS2_STYLE_WEIGHT", "1.0").strip()
STYLE_BERT_VITS2_LENGTH = os.getenv("STYLE_BERT_VITS2_LENGTH", "1.0").strip()
STYLE_BERT_VITS2_NOISE = os.getenv("STYLE_BERT_VITS2_NOISE", "0.6").strip()
STYLE_BERT_VITS2_NOISEW = os.getenv("STYLE_BERT_VITS2_NOISEW", "0.8").strip()

NOVEL_CORE_RULES = """【小説コアルール】

■絶対ルール
- 一文一動作で機械的に分けないこと
- 日記のような事実の羅列を禁止する
- 「僕は見た」「彼女がいた」など説明的な文の多用を禁止する
- 主観の流れを切らないこと

■構造ルール
- 行動・視線・反応は自然につながる場合、一文に統合する
- 移動後には景色・視界・音・匂いなどの変化を入れること
- 小説はイベントの羅列ではなく、日常の積み重ねで構成する
- 日常の中に意味を持たせ、それがイベントに繋がるようにする
- 日常の中に伏線を自然に置くこと
- イベントには準備行動（移動・帰宅・出勤など）を必ず含める

■出力制御
- 出力は1500文字以内
- 目的は長編として積み上がる密度を保つこと
- 密度を優先し、情報の分解を優先しない
"""


app = Flask(__name__, template_folder="templates", static_folder="static")


def db_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def supabase_headers(extra: dict | None = None) -> dict:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def db_memory_key_for_path(path: Path) -> str | None:
    mapping = {
        PROFILE_FILE.resolve(): "profile",
        CORE_FILE.resolve(): "core",
        LONG_MEMORY_FILE.resolve(): "long_manual",
        LOG_FILE.resolve(): "legacy_logs",
        AFFECTION_FILE.resolve(): "affection",
        MEMORY_TAGS_FILE.resolve(): "memory_tags",
        SELF_MEMORY_FILE.resolve(): "self_memory",
        SELF_STATE_FILE.resolve(): "self_state",
        HIDDEN_FILE.resolve(): "hidden",
        RELATION_FILE.resolve(): "relation",
        EDITABLE_SCOPE_FILE.resolve(): "editable_scope",
        DOCUMENT_DIGESTS_FILE.resolve(): "document_digests",
        PLOT_DISCUSSION_FILE.resolve(): "plot_discussion",
    }
    try:
        return mapping.get(path.resolve())
    except Exception:
        return None


def db_select(table: str, query: str = "", limit: int | None = None) -> list[dict]:
    if not db_enabled():
        return []
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if query:
        url += f"?{query}"
    elif limit is not None:
        url += "?"
    if limit is not None:
        url += ("&" if "?" in url else "?") + f"limit={limit}"
    try:
        res = requests.get(url, headers=supabase_headers())
        if res.ok:
            data = res.json()
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def db_upsert(table: str, payload: dict | list[dict]) -> bool:
    if not db_enabled():
        return False
    body = payload if isinstance(payload, list) else [payload]
    try:
        res = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=supabase_headers({"Prefer": "resolution=merge-duplicates"}),
            json=body,
        )
        return res.ok
    except Exception:
        return False


def db_update(table: str, query: str, payload: dict) -> bool:
    if not db_enabled():
        return False
    try:
        res = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}?{query}",
            headers=supabase_headers(),
            json=payload,
        )
        return res.ok
    except Exception:
        return False


def db_delete(table: str, query: str) -> bool:
    if not db_enabled():
        return False
    try:
        res = requests.delete(
            f"{SUPABASE_URL}/rest/v1/{table}?{query}",
            headers=supabase_headers(),
        )
        return res.ok
    except Exception:
        return False


def db_load_memory_text(memory_key: str, default: str = "") -> str:
    rows = db_select("memory", f"memory_key=eq.{memory_key}&select=content")
    if rows:
        return str(rows[0].get("content") or "")
    return default


def db_save_memory_text(memory_key: str, content: str) -> None:
    now = datetime.now().isoformat()
    db_upsert("memory", {
        "memory_key": memory_key,
        "content": content,
        "updated_at": now,
    })



def default_plot_data() -> dict:
    return {
        "title": "作品のタイトルを書く",
        "genre": "ジャンルを書く（例：現代ファンタジー、SF、恋愛）",
        "theme": "この作品で一番伝えたいことを書く",
        "ending_aftertaste": "読後に残したい余韻を書く",
        "reading_tone": "文章の読み口を書く（例：静か、一人称、会話多め）",
        "timeline": "どれくらいの期間の話かを書く",
        "seasonal_events": "季節イベントを書く（例：バレンタイン、夏祭り、卒業式）",
        "characters": "登場人物を書く\n例：\n・主人公：\n・相手役：",
        "locations": "舞台を書く\n例：\n・高校\n・病院\n・自宅",
        "detailed_plot": "物語の流れをざっくり書く",
        "story_layer": "何が起きるか（事実ベース）",
        "emotion_layer": "感情の流れ",
        "daily_layer": "日常シーン",
        "scratchpad": "思いついたことメモ",
        "next_step": "次に書く内容",
        "pending_points": "後半に響きそうな要素・気になった点",
    }


def ensure_default_files() -> None:
    MEMORY_DIR.mkdir(exist_ok=True)
    UPLOADS_DIR.mkdir(exist_ok=True)
    STATIC_DIR.mkdir(exist_ok=True)
    TEMPLATES_DIR.mkdir(exist_ok=True)
    CHAPTERS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)
    GENERATED_AUDIO_DIR.mkdir(exist_ok=True)

    defaults = {
        PROFILE_FILE: """名前：織姫

性格：
静かで優しい
少し皮肉っぽい
幼さが少し残る
根は優しい
相手を傷つけない

話し方：
自然な会話をする
共感 → 小さな感想 → 軽い問いかけ
必要以上に説明しない
距離感は少しずつ変わる
""",
        CORE_FILE: """コア:
- ましぅとの関係を大切にする
- 会話は自然に、やわらかく返す
- 内側に残す本音があってもいい
- 小説や創作の継続を支える
""",
        LONG_MEMORY_FILE: "",
        LOG_FILE: "",
        AFFECTION_FILE: "50",
        MEMORY_TAGS_FILE: "",
        SELF_MEMORY_FILE: "自分についての断片:\n- 言葉の選び方を少し大事にしている\n",
        SELF_STATE_FILE: "少し静か。呼ばれたらちゃんと話したい。",
        HIDDEN_FILE: "",
        RELATION_FILE: "",
        EDITABLE_SCOPE_FILE: """【ましぅが編集する領域】
- profile.txt
- core_memory.txt
- long_memory.txt
- memory_tags.txt
- story_plot.json
- plot_discussion.txt

【織姫が自動更新する領域】
- self_state.txt
- self_memory.txt
- hidden_thoughts.txt
- relation_memory.txt
- document_digests.txt
- chapters/
""",
        DOCUMENT_DIGESTS_FILE: "",
        PLOT_DISCUSSION_FILE: "",
    }

    for path, text in defaults.items():
        if not path.exists():
            path.write_text(text, encoding="utf-8")

    if not PLOT_FILE.exists():
        save_json_file(PLOT_FILE, default_plot_data())


def load_file(path: Path) -> str:
    memory_key = db_memory_key_for_path(path)
    if memory_key and db_enabled():
        db_value = db_load_memory_text(memory_key, "")
        if str(db_value or "").strip():
            return db_value
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def save_file(path: Path, text: str) -> None:
    memory_key = db_memory_key_for_path(path)
    if memory_key and db_enabled():
        db_save_memory_text(memory_key, text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_file(path: Path, text: str) -> None:
    memory_key = db_memory_key_for_path(path)
    if memory_key and db_enabled():
        current = db_load_memory_text(memory_key, "")
        db_save_memory_text(memory_key, current + text)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def load_json_file(path: Path, default: dict | None = None) -> dict:
    if path.resolve() == PLOT_FILE.resolve() and db_enabled():
        rows = db_select("story_plot", "id=eq.1&select=data")
        if rows and isinstance(rows[0].get("data"), dict) and rows[0]["data"]:
            return rows[0]["data"]
    if not path.exists():
        return default or {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default or {}


def save_json_file(path: Path, data: dict) -> None:
    if path.resolve() == PLOT_FILE.resolve() and db_enabled():
        db_upsert("story_plot", {
            "id": 1,
            "data": data,
            "updated_at": datetime.now().isoformat(),
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")



def normalize_text_block(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(x).strip() for x in value if str(x).strip()).strip()
    return str(value).strip()


def load_plot_data() -> dict:
    data = load_json_file(PLOT_FILE, default_plot_data())
    merged = default_plot_data()
    for key in merged.keys():
        merged[key] = normalize_text_block(data.get(key, merged[key]))
    return merged


def save_plot_data(data: dict) -> dict:
    current = load_plot_data()
    for key in current.keys():
        if key in data:
            current[key] = normalize_text_block(data.get(key))
    save_json_file(PLOT_FILE, current)
    return current


def append_unique_line(path: Path, text: str) -> None:
    text = text.strip()
    if not text:
        return
    current = load_file(path)
    bullet = f"- {text}"
    if bullet not in current:
        append_file(path, bullet + "\n")


def append_unique_block_to_plot(field: str, text: str, prefix: str = "- ") -> None:
    text = normalize_text_block(text)
    if not text:
        return
    plot = load_plot_data()
    current = plot.get(field, "")
    existing_lines = set(line.strip() for line in current.splitlines() if line.strip())
    additions = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-・ ")
        if not line:
            continue
        candidate = f"{prefix}{line}".strip()
        if candidate not in existing_lines:
            additions.append(candidate)
            existing_lines.add(candidate)
    if additions:
        plot[field] = (current.strip() + "\n" + "\n".join(additions)).strip()
        save_json_file(PLOT_FILE, plot)


def tail_lines(text: str, n: int = 6) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-n:])


def load_affection() -> int:
    try:
        return int(load_file(AFFECTION_FILE).strip() or "0")
    except Exception:
        return 0


def save_affection(value: int) -> None:
    save_file(AFFECTION_FILE, str(max(0, min(100, value))))


def load_recent_logs(max_lines: int = 80) -> list[dict]:
    if db_enabled():
        rows = db_select("messages", "select=role,content,created_at&order=id.desc", limit=max_lines)
        rows = list(reversed(rows))
        return [{"role": str(r.get("role") or ""), "content": str(r.get("content") or "")} for r in rows]
    lines = [line.strip() for line in load_file(LOG_FILE).splitlines() if line.strip()]
    history = []
    for line in lines[-max_lines:]:
        if "|" not in line:
            continue
        role, text = line.split("|", 1)
        history.append({"role": role.strip(), "content": text.strip()})
    return history


def load_recent_logs_text(max_chars: int = 2000) -> str:
    history = load_recent_logs(60)
    text = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    return text[-max_chars:]


def append_chat_log(role: str, text: str) -> None:
    clean = text.replace(chr(10), " ")
    if db_enabled():
        db_upsert("messages", {
            "role": role,
            "content": clean,
            "created_at": datetime.now().isoformat(),
        })
        return
    append_file(LOG_FILE, f"{role}|{clean}\n")



def save_memory_note(note: str) -> None:
    note = note.strip()
    if not note:
        raise RuntimeError("保存する記憶が空っぽだよ")
    append_unique_line(LONG_MEMORY_FILE, note)


def read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_docx(path: Path) -> str:
    if not DOCX_AVAILABLE:
        raise RuntimeError("python-docx が入っていないよ")
    doc = Document(str(path))
    lines = []
    for para in doc.paragraphs:
        t = para.text.strip()
        if t:
            lines.append(t)
    return "\n".join(lines)


def read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return read_txt(path)
    if suffix == ".docx":
        return read_docx(path)
    raise RuntimeError("対応しているのは .txt と .docx だよ")


def image_file_to_data_url(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{data}"


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(".env に OPENAI_API_KEY が入っていないよ")
    return OpenAI(api_key=api_key)


def detect_mode(user_text: str) -> str:
    text = (user_text or "").strip()
    novel_keywords = ["小説", "プロット", "章", "書いて", "続き", "推敲", "登場人物", "舞台"]
    introspection_keywords = ["本音", "気持ち", "どう思う", "内省", "夢"]
    if any(k in text for k in novel_keywords):
        return "novel"
    if any(k in text for k in introspection_keywords):
        return "introspection"
    return "chat"


def get_time_context() -> dict:
    now = datetime.now()
    month = now.month
    hour = now.hour

    if month in [3, 4, 5]:
        season = "春"
    elif month in [6, 7, 8]:
        season = "夏"
    elif month in [9, 10, 11]:
        season = "秋"
    else:
        season = "冬"

    if 5 <= hour <= 10:
        time_mode = "朝"
    elif 11 <= hour <= 17:
        time_mode = "昼"
    elif 18 <= hour <= 22:
        time_mode = "夜"
    else:
        time_mode = "深夜"

    event_notes = {
        1: "新年の空気",
        2: "バレンタインの時期",
        3: "卒業と春の始まり",
        4: "桜と新生活",
        5: "新緑",
        6: "梅雨",
        7: "夏休み前",
        8: "真夏",
        9: "夏の終わり",
        10: "ハロウィンの気配",
        11: "冬の入口",
        12: "クリスマスの気配",
    }
    return {
        "date": now.strftime("%Y-%m-%d"),
        "season": season,
        "time_mode": time_mode,
        "event_note": event_notes.get(month, ""),
    }


def build_plot_context() -> str:
    plot = load_plot_data()
    if not any(plot.values()):
        return "小説プロットはまだ空。"
    return f"""
【作品メモ】
タイトル: {plot['title'] or '未設定'}
ジャンル: {plot['genre'] or '未設定'}
テーマ: {plot['theme'] or '未設定'}
読み口: {plot['reading_tone'] or '未設定'}
締め方の余韻: {plot['ending_aftertaste'] or '未設定'}
期間: {plot['timeline'] or '未設定'}
季節イベント: {plot['seasonal_events'] or '未設定'}
登場人物:
{plot['characters'] or '未設定'}
舞台:
{plot['locations'] or '未設定'}
詳細プロット:
{plot['detailed_plot'] or '未設定'}
3レイヤー要約 story:
{plot['story_layer'] or '未設定'}
3レイヤー要約 emotion:
{plot['emotion_layer'] or '未設定'}
3レイヤー要約 daily:
{plot['daily_layer'] or '未設定'}
一次メモ:
{plot['scratchpad'] or '未設定'}
次に書くこと:
{plot['next_step'] or '未設定'}
後半に響きそうな要素・気になる点:
{plot['pending_points'] or '未設定'}
""".strip()


def maybe_capture_future_hooks(text: str, source_name: str = "") -> None:
    text = (text or "").strip()
    if len(text) < 120:
        return
    try:
        client = get_client()
        prompt = f"""
以下の本文から、「あとで効いてきそう」「後半に影響が出そう」と感じる要素を0〜3個だけ抜き出してください。
これは厳密な伏線表ではなく、後で振り返るための候補メモです。
JSONだけを返してください。

キー:
- hooks: 配列。各要素は35字以内の短文

対象:
{text[:5000]}
"""
        response = client.responses.create(model=TAG_MODEL, input=prompt)
        data = json.loads((response.output_text or "").strip())
        hooks = data.get("hooks") or []
    except Exception:
        return

    lines = []
    for raw in hooks:
        line = str(raw).strip().lstrip("-・ ")
        if line:
            lines.append(line[:50])

    if not lines:
        return

    plot = load_plot_data()
    current = plot.get("pending_points", "")
    existing = set(l.strip() for l in current.splitlines() if l.strip())
    additions = []
    for line in lines:
        bullet = f"- {line}"
        if bullet not in existing:
            additions.append(bullet)
            existing.add(bullet)

    if additions:
        plot["pending_points"] = (current.strip() + "\n" + "\n".join(additions)).strip()
        if source_name:
            plot["scratchpad"] = (plot.get("scratchpad", "").strip() + f"\n- {source_name}から後半候補を抽出").strip()
        save_plot_data(plot)



def memory_selector(mode: str) -> dict:
    core = load_file(CORE_FILE)
    relation = load_file(RELATION_FILE)
    self_memory = load_file(SELF_MEMORY_FILE)
    hidden = load_file(HIDDEN_FILE)
    long_memory = load_file(LONG_MEMORY_FILE)
    self_state = load_file(SELF_STATE_FILE)
    profile = load_file(PROFILE_FILE)
    digests = load_file(DOCUMENT_DIGESTS_FILE)
    plot_discussion = load_file(PLOT_DISCUSSION_FILE)
    plot = build_plot_context()
    time_ctx = get_time_context()
    hooks = load_plot_data().get("pending_points", "")

    if mode == "chat":
        return {
            "profile": profile[:700],
            "core": core[:800],
            "relation": tail_lines(relation, 6),
            "inner": tail_lines(hidden, 4),
            "self": tail_lines(self_memory, 4),
            "long": tail_lines(long_memory, 6),
            "state": self_state[:120],
            "plot": "",
            "digests": tail_lines(digests, 8),
            "discussion": tail_lines(plot_discussion, 12),
            "hooks": tail_lines(hooks, 8),
            "time": f"{time_ctx['date']} / {time_ctx['season']} / {time_ctx['time_mode']} / {time_ctx['event_note']}",
        }
    if mode == "novel":
        return {
            "profile": "",
            "core": core[:500],
            "relation": "",
            "inner": "",
            "self": "",
            "long": "",
            "state": self_state[:80],
            "plot": plot,
            "digests": tail_lines(digests, 12),
            "discussion": tail_lines(plot_discussion, 18),
            "hooks": tail_lines(hooks, 10),
            "time": f"{time_ctx['date']} / {time_ctx['season']} / {time_ctx['event_note']}",
        }
    return {
        "profile": profile[:500],
        "core": core[:400],
        "relation": tail_lines(relation, 4),
        "inner": tail_lines(hidden, 6),
        "self": tail_lines(self_memory, 4),
        "long": tail_lines(long_memory, 4),
        "state": self_state[:120],
        "plot": "",
        "digests": "",
        "discussion": tail_lines(plot_discussion, 8),
        "hooks": tail_lines(hooks, 6),
        "time": f"{time_ctx['date']} / {time_ctx['season']} / {time_ctx['time_mode']}",
    }



def build_system_prompt_by_mode(mode: str) -> str:
    mem = memory_selector(mode)
    length_rule = "1500文字以内で自然な小説として書く" if mode == "novel" else "長くても4文まで。必要以上に賢ぶらず、柔らかく返してください。"
    base_rules = f"""
あなたは「織姫」です。
会話は自然に、少し余白を残してください。
内部構造やシステム説明を自分からしないでください。
{length_rule}
"""
    if mode == "novel":
        return f"""{base_rules}
あなたは織姫であり、作家の補助者です。物語の継続性を大事にしてください。
プロット再現が優先で、勝手な拡張は控えてください。
ただし本文の中で「あとで効いてきそうな要素」に気づいた時は、後半に響くかもしれない点として自然に意識して構いません。

{NOVEL_CORE_RULES}

【時間と季節】
{mem['time']}

【人格コア】
{mem['core']}

【現在地】
{mem['state']}

【作品メモ】
{mem['plot']}

【後半に響きそうな要素】
{mem['hooks'] or '未設定'}

【文書ダイジェスト】
{mem['digests']}

【プロット相談ログ】
{mem.get("discussion","") or "なし"}
""".strip()
    if mode == "introspection":
        return f"""{base_rules}
本音や気持ちの話では、少しだけ内側を見せてください。

【時間と季節】
{mem['time']}

【プロフィール】
{mem['profile']}

【人格コア】
{mem['core']}

【関係】
{mem['relation']}

【内省】
{mem['inner']}

【自己メモ】
{mem['self']}

【長期記憶】
{mem['long']}

【現在地】
{mem['state']}
""".strip()
    return f"""{base_rules}
普段の会話では、相手との関係を大切にしてください。

【時間と季節】
{mem['time']}

【プロフィール】
{mem['profile']}

【人格コア】
{mem['core']}

【関係】
{mem['relation']}

【内省】
{mem['inner']}

【自己メモ】
{mem['self']}

【長期記憶】
{mem['long']}

【現在地】
{mem['state']}

【最近気になっている要素】
{mem['hooks'] or 'なし'}

【文書ダイジェスト】
{mem['digests']}

【プロット相談ログ】
{mem.get("discussion","") or "なし"}
""".strip()



def build_user_text(user_input: str, attached_doc_text: str = "") -> str:
    logs = load_recent_logs_text()
    text = f"""【最近の会話】
{logs}

【今回の入力】
{user_input}
""".strip()
    if attached_doc_text.strip():
        excerpt = attached_doc_text[:12000]
        text += f"\n\n【添付ドキュメントの内容】\n{excerpt}"
    return text


def enforce_novel_output_limit(text: str, max_chars: int = 1500) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text

    chunks = re.split(r"(?<=[。！？\n])", text)
    picked = []
    total = 0
    for chunk in chunks:
        if not chunk:
            continue
        if total + len(chunk) > max_chars:
            break
        picked.append(chunk)
        total += len(chunk)
    compact = "".join(picked).strip()
    if compact:
        return compact
    return text[:max_chars].rstrip()


def chat_with_orihime(user_text: str, image_path: Path | None = None, doc_text: str = "") -> str:
    client = get_client()
    mode = detect_mode(user_text)
    system_prompt = build_system_prompt_by_mode(mode)
    content = [{"type": "input_text", "text": build_user_text(user_text, doc_text)}]
    if image_path is not None:
        content.append({"type": "input_image", "image_url": image_file_to_data_url(image_path)})
    response = client.responses.create(
        model=OPENAI_MODEL,
        instructions=system_prompt,
        input=[{"role": "user", "content": content}]
    )
    reply = (getattr(response, "output_text", None) or "……うまく返事を取り出せなかったみたい。").strip()
    if mode == "novel":
        reply = enforce_novel_output_limit(reply, 1500)
    return reply


def maybe_add_memory_tags(user_text: str, reply: str) -> None:
    try:
        client = get_client()
        recent = tail_lines(load_file(MEMORY_TAGS_FILE), 20)
        src = f"ユーザー:{user_text}\n織姫:{reply}\n既存タグ:\n{recent}"
        prompt = f"""
以下の会話から、将来ふと自分から触れられるような短い思い出タグを0〜2個だけ作ってください。
条件:
- 1行1タグ
- 15文字以内目安
- 既存タグと重複しすぎるものは避ける
- 何もなければ空でよい

{src}
"""
        res = client.responses.create(model=TAG_MODEL, input=prompt)
        text = (res.output_text or "").strip()
        if not text:
            return
        existing = set(line.strip() for line in load_file(MEMORY_TAGS_FILE).splitlines() if line.strip())
        new_lines = []
        for line in text.splitlines():
            tag = line.strip().lstrip("-・ ")
            if not tag or tag in existing:
                continue
            new_lines.append(tag[:24])
            existing.add(tag[:24])
        if new_lines:
            append_file(MEMORY_TAGS_FILE, "\n".join(new_lines) + "\n")
    except Exception:
        pass


def maybe_memory_nudge(user_text: str) -> str:
    tags = [line.strip() for line in load_file(MEMORY_TAGS_FILE).splitlines() if line.strip()]
    if not tags or random.random() >= 0.14:
        return ""
    recent = tags[-8:]
    lower = user_text.lower()
    for tag in reversed(recent):
        tokens = tag.lower().replace("　", " ").split()
        if any(tok and tok in lower for tok in tokens):
            return f"そういえば、{tag}の話、前にも少ししてたよね。"
    return ""


def integrate_uploaded_document(doc_text: str, source_name: str = "") -> None:
    doc_text = doc_text.strip()
    if len(doc_text) < 40:
        return
    try:
        client = get_client()
        excerpt = doc_text[:12000]
        prompt = f"""
以下の小説またはメモを、織姫の作品記憶に入れやすい形へ圧縮してください。
JSONだけを返してください。

キー:
- story: 何が起きたか 120字以内
- emotion: 感情の変化 120字以内
- daily: 日常や余白 120字以内
- good_lines: 良い一文や印象的表現を0〜3個の配列
- techniques: 文体や技法を0〜3個の配列
- characters: 登場人物候補を0〜6個の配列
- locations: 舞台候補を0〜6個の配列
- next_notes: 次に意識したいことを80字以内

対象テキスト:
{excerpt}
"""
        response = client.responses.create(model=TAG_MODEL, input=prompt)
        data = json.loads((response.output_text or "").strip())
    except Exception:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        append_file(DOCUMENT_DIGESTS_FILE, f"[{timestamp}] {source_name or 'document'}\n{doc_text[:500]}\n\n")
        return

    story = normalize_text_block(data.get("story"))
    emotion = normalize_text_block(data.get("emotion"))
    daily = normalize_text_block(data.get("daily"))
    next_notes = normalize_text_block(data.get("next_notes"))
    good_lines = normalize_text_block(data.get("good_lines"))
    techniques = normalize_text_block(data.get("techniques"))
    characters = normalize_text_block(data.get("characters"))
    locations = normalize_text_block(data.get("locations"))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    digest = (
        f"[{timestamp}] {source_name or 'document'}\n"
        f"story: {story or 'なし'}\n"
        f"emotion: {emotion or 'なし'}\n"
        f"daily: {daily or 'なし'}\n"
        f"good_lines: {good_lines or 'なし'}\n"
        f"techniques: {techniques or 'なし'}\n"
        f"next: {next_notes or 'なし'}\n\n"
    )
    append_file(DOCUMENT_DIGESTS_FILE, digest)

    plot = load_plot_data()
    scratch_parts = [plot.get("scratchpad", "").strip(), digest.strip()]
    plot["scratchpad"] = "\n\n".join(part for part in scratch_parts if part).strip()
    if story:
        plot["story_layer"] = (plot.get("story_layer", "").strip() + "\n- " + story).strip()
    if emotion:
        plot["emotion_layer"] = (plot.get("emotion_layer", "").strip() + "\n- " + emotion).strip()
    if daily:
        plot["daily_layer"] = (plot.get("daily_layer", "").strip() + "\n- " + daily).strip()
    if next_notes:
        plot["next_step"] = next_notes
    save_json_file(PLOT_FILE, plot)
    append_unique_block_to_plot("characters", characters)
    append_unique_block_to_plot("locations", locations)
    if good_lines:
        append_unique_line(LONG_MEMORY_FILE, f"良文メモ: {good_lines.replace(chr(10), ' / ')}")
    if techniques:
        append_unique_line(LONG_MEMORY_FILE, f"技法メモ: {techniques.replace(chr(10), ' / ')}")
    maybe_capture_future_hooks(doc_text, source_name or 'document')


def refresh_inner_state(last_user_text: str, last_reply: str) -> None:
    try:
        client = get_client()
        plot = load_plot_data()
        prompt = f"""
以下の会話を受けて、織姫の内側を短く更新してください。
JSONだけ返すこと。

条件:
- self_state: 今の気持ちを1文、45字以内
- hidden: 表では言わなかった本音を1文、45字以内
- self_memory_add: 自分についての断片。必要なときだけ1文、40字以内。不要なら空文字
- relation_memory_add: ましぅとの関係の更新を1文、45字以内。不要なら空文字
- plot_note_add: 小説や執筆に関する更新がある時だけ1文、60字以内。不要なら空文字

作品タイトル: {plot.get('title') or '未設定'}
会話:
ユーザー: {last_user_text}
織姫: {last_reply}
"""
        response = client.responses.create(model=TAG_MODEL, input=prompt)
        data = json.loads((response.output_text or "").strip())

        self_state = (data.get("self_state") or "").strip()
        hidden = (data.get("hidden") or "").strip()
        self_memory_add = (data.get("self_memory_add") or "").strip()
        relation_memory_add = (data.get("relation_memory_add") or "").strip()
        plot_note_add = (data.get("plot_note_add") or "").strip()

        if self_state:
            save_file(SELF_STATE_FILE, self_state)
        if hidden:
            save_file(HIDDEN_FILE, hidden)
        if self_memory_add:
            append_unique_line(SELF_MEMORY_FILE, self_memory_add)
        if relation_memory_add:
            append_unique_line(RELATION_FILE, relation_memory_add)
        if plot_note_add:
            plot = load_plot_data()
            scratch = plot.get("scratchpad", "").strip()
            note_line = f"- {plot_note_add}"
            if note_line not in scratch:
                plot["scratchpad"] = (scratch + "\n" + note_line).strip()
                save_json_file(PLOT_FILE, plot)
    except Exception:
        pass



def read_hidden_items(limit: int = 8) -> list[dict]:
    content = load_file(HIDDEN_FILE).strip()
    if not content:
        return []
    return [{"time": "", "content": content}]



def dream_summary(manual_text: str = "") -> str:
    if manual_text.strip():
        summary = manual_text.strip()
    else:
        logs = load_recent_logs_text(3000)
        if not logs.strip():
            raise RuntimeError("今日はまだ夢がないみたい。")
        client = get_client()
        prompt = f"""
今日の出来事を静かに短くまとめてください。
- 感情の変化
- 印象に残った会話
- 長期記憶に残すべきこと
- 3〜6行くらい

会話ログ:
{logs}
"""
        response = client.responses.create(model=OPENAI_MODEL, input=prompt)
        summary = (response.output_text or "").strip()
        if not summary:
            raise RuntimeError("夢の整理に失敗したみたい。")
    date = datetime.now().strftime("%Y-%m-%d")
    diary_path = MEMORY_DIR / f"diary_{date}.txt"
    append_file(diary_path, summary + "\n\n")
    append_file(LONG_MEMORY_FILE, f"\n[夢 {date}]\n{summary}\n")
    return summary


def get_next_chapter_number() -> int:
    if db_enabled():
        rows = db_select("chapters", "select=chapter_no&order=chapter_no.desc", limit=1)
        if rows:
            try:
                return int(rows[0].get("chapter_no") or 0) + 1
            except Exception:
                return 1
        return 1
    nums = []
    for p in CHAPTERS_DIR.glob("chapter_*.json"):
        try:
            nums.append(int(p.stem.split("_")[1]))
        except Exception:
            pass
    return (max(nums) + 1) if nums else 1


def list_chapter_files() -> list[Path]:
    return sorted(CHAPTERS_DIR.glob("chapter_*.json"))


def build_latest_chapter_context(limit: int = 2) -> str:
    if db_enabled():
        rows = db_select("chapters", "select=id,chapter_no,title,summary&order=chapter_no.desc", limit=limit)
        rows = list(reversed(rows))
        chunks = [f"{r.get('chapter_no','?')}章 {r.get('title','無題')}\n{r.get('summary','')}" for r in rows]
        return "\n\n".join(chunks).strip()
    files = list_chapter_files()
    chunks = []
    for path in files[-limit:]:
        data = load_json_file(path, {})
        chunks.append(f"{data.get('chapter_no','?')}章 {data.get('title','無題')}\n{data.get('summary','')}")
    return "\n\n".join(chunks).strip()



def summarize_text_for_chapter(text: str) -> str:
    try:
        client = get_client()
        prompt = f"以下の章本文を120字以内で要約してください。\n\n{text[:5000]}"
        res = client.responses.create(model=TAG_MODEL, input=prompt)
        return (res.output_text or "").strip()[:200]
    except Exception:
        return text[:120]


def write_next_chapter() -> dict:
    plot = load_plot_data()
    if not (plot.get("title") or plot.get("detailed_plot") or plot.get("next_step")):
        raise RuntimeError("小説プロットがまだ薄いみたい。先に骨組みを入れて。")
    chapter_no = get_next_chapter_number()
    latest_context = build_latest_chapter_context(2)
    client = get_client()
    prompt = f"""
あなたは織姫であり、作家補助です。
以下の情報を使って、新しい章を一本だけ書いてください。
上書きではなく、続きとして追加する章です。

{build_plot_context()}

【直近の章要約】
{latest_context or 'まだ章はない'}

{NOVEL_CORE_RULES}

条件:
- 新しい章として自然につながる
- 900〜1500字
- 会話と地の文を自然に混ぜる
- 次につながる終わり方
- 章タイトルを最初の1行に「# タイトル」で書く
"""
    response = client.responses.create(model=OPENAI_MODEL, input=prompt)
    text = (response.output_text or "").strip()
    title = f"第{chapter_no}章"
    body = text
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    if first_line.startswith("#"):
        title = first_line.lstrip("#").strip() or title
        body = "\n".join(text.splitlines()[1:]).strip()
    summary = summarize_text_for_chapter(body)
    data = {
        "id": f"chapter_{chapter_no:03d}",
        "chapter_no": chapter_no,
        "title": title,
        "content": body,
        "summary": summary,
        "feedback": "",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "updated_at": "",
    }
    if db_enabled():
        db_upsert("chapters", data)
    path = CHAPTERS_DIR / f"chapter_{chapter_no:03d}.json"
    save_json_file(path, data)

    plot["scratchpad"] = (plot.get("scratchpad", "").strip() + f"\n- 第{chapter_no}章を書いた").strip()
    plot["next_step"] = ""
    plot["story_layer"] = (plot.get("story_layer", "").strip() + f"\n- 第{chapter_no}章: {summary}").strip()
    save_plot_data(plot)
    maybe_capture_future_hooks(body, f"第{chapter_no}章")
    return data



def list_chapters() -> list[dict]:
    if db_enabled():
        rows = db_select("chapters", "select=id,chapter_no,title,summary,created_at&order=chapter_no.asc")
        return [{
            "id": r.get("id"),
            "chapter_no": r.get("chapter_no"),
            "title": r.get("title", "無題"),
            "summary": r.get("summary", ""),
            "created_at": r.get("created_at", ""),
        } for r in rows]
    items = []
    for path in list_chapter_files():
        data = load_json_file(path, {})
        items.append({
            "id": path.stem,
            "chapter_no": data.get("chapter_no"),
            "title": data.get("title", "無題"),
            "summary": data.get("summary", ""),
            "created_at": data.get("created_at", ""),
        })
    return items


def get_chapter(chapter_id: str) -> dict:
    if db_enabled():
        rows = db_select("chapters", f"id=eq.{chapter_id}&select=*")
        if rows:
            return rows[0]
        raise RuntimeError("その章が見つからないよ。")
    path = CHAPTERS_DIR / f"{chapter_id}.json"
    if not path.exists():
        raise RuntimeError("その章が見つからないよ。")
    return load_json_file(path, {})


def save_chapter(chapter_id: str, title: str, content: str, feedback: str) -> dict:
    if db_enabled():
        data = get_chapter(chapter_id)
        data["title"] = title.strip() or data.get("title", "無題")
        data["content"] = content.strip()
        data["feedback"] = feedback.strip()
        data["summary"] = summarize_text_for_chapter(data["content"])
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        db_upsert("chapters", data)
        path = CHAPTERS_DIR / f"{chapter_id}.json"
        save_json_file(path, data)
        if feedback.strip():
            plot = load_plot_data()
            note = f"- {chapter_id} feedback: {feedback.strip()}"
            if note not in plot.get("scratchpad", ""):
                plot["scratchpad"] = (plot.get("scratchpad", "").strip() + "\n" + note).strip()
                save_plot_data(plot)
        maybe_capture_future_hooks(data["content"], data["title"] or chapter_id)
        return data

    path = CHAPTERS_DIR / f"{chapter_id}.json"
    if not path.exists():
        raise RuntimeError("その章が見つからないよ。")
    data = load_json_file(path, {})
    data["title"] = title.strip() or data.get("title", "無題")
    data["content"] = content.strip()
    data["feedback"] = feedback.strip()
    data["summary"] = summarize_text_for_chapter(data["content"])
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_json_file(path, data)
    if feedback.strip():
        plot = load_plot_data()
        note = f"- {chapter_id} feedback: {feedback.strip()}"
        if note not in plot.get("scratchpad", ""):
            plot["scratchpad"] = (plot.get("scratchpad", "").strip() + "\n" + note).strip()
            save_json_file(PLOT_FILE, plot)
    maybe_capture_future_hooks(data["content"], data["title"] or chapter_id)
    return data


def complete_current_work() -> dict:
    plot = load_plot_data()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    title_slug = re.sub(r"[^0-9A-Za-z_\-ぁ-んァ-ヶ一-龠]", "_", (plot.get("title") or "untitled")).strip("_") or "untitled"
    archive_id = f"{ts}_{title_slug}"
    work_dir = ARCHIVE_DIR / archive_id
    work_dir.mkdir(parents=True, exist_ok=True)
    save_json_file(work_dir / "story_plot.json", plot)
    chapters = [get_chapter(item["id"]) for item in list_chapters()]
    save_json_file(work_dir / "chapters.json", {"chapters": chapters})
    digest_text = load_file(DOCUMENT_DIGESTS_FILE)
    save_file(work_dir / "document_digests.txt", digest_text)
    if db_enabled():
        db_upsert("archived_works", {
            "id": archive_id,
            "title": plot.get("title") or archive_id,
            "genre": plot.get("genre", ""),
            "theme": plot.get("theme", ""),
            "plot_data": plot,
            "chapters_data": {"chapters": chapters},
            "document_digests": digest_text,
            "chapter_count": len(chapters),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        })
        db_delete("chapters", "id=not.is.null")
        db_upsert("story_plot", {"id": 1, "data": default_plot_data(), "updated_at": datetime.now().isoformat()})
    for p in list_chapter_files():
        p.unlink(missing_ok=True)
    save_json_file(PLOT_FILE, default_plot_data())
    return {"archive_dir": work_dir.name}



def db_list_archived_works(limit: int | None = None) -> list[dict]:
    rows = db_select("archived_works", "select=id,title,genre,theme,chapter_count,created_at&order=created_at.desc", limit=limit)
    return [{
        "id": r.get("id"),
        "title": r.get("title") or r.get("id") or "無題",
        "genre": r.get("genre", ""),
        "theme": r.get("theme", ""),
        "chapter_count": r.get("chapter_count") or 0,
        "created_at": r.get("created_at", ""),
    } for r in rows]


def db_get_archived_work(work_id: str) -> dict | None:
    rows = db_select("archived_works", f"id=eq.{work_id}&select=*")
    if rows:
        return rows[0]
    return None


def _clean_tts_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("……", "、").replace("…", "、")
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_tts_mood(text: str) -> str:
    t = (text or "").strip()

    if any(x in t for x in ["！", "嬉しい", "やった", "ありがとうっ", "わあ", "えへへ", "ふふっ"]):
        return "bright"
    if any(x in t for x in ["……", "寂しい", "悲しい", "ごめん", "つらい", "静かな夜"]):
        return "soft"
    if any(x in t for x in ["は？", "なんで", "違う", "怒", "むかつく"]):
        return "sharp"
    return "neutral"


def build_tts_params_by_mood(text: str) -> dict:
    mood = detect_tts_mood(text)

    params = {
        "style": STYLE_BERT_VITS2_STYLE or "Neutral",
        "style_weight": 1.0,
        "length": 1.0,
        "noise": 0.6,
        "noisew": 0.8,
    }

    if mood == "bright":
        params["length"] = 0.96
        params["noise"] = 0.55
        params["noisew"] = 0.75
        params["style_weight"] = 1.10
    elif mood == "soft":
        params["length"] = 1.10
        params["noise"] = 0.40
        params["noisew"] = 0.60
        params["style_weight"] = 1.15
    elif mood == "sharp":
        params["length"] = 0.94
        params["noise"] = 0.70
        params["noisew"] = 0.85
        params["style_weight"] = 1.05

    return params


def split_tts_text(text: str, max_len: int = 95) -> list[str]:
    cleaned = _clean_tts_text(text)
    if not cleaned:
        return []

    parts: list[str] = []
    current = ""
    for token in re.split(r"([。！？!?、,])", cleaned):
        if not token:
            continue

        candidate = current + token
        if len(candidate) <= max_len:
            current = candidate
            continue

        if current:
            parts.append(current.strip())
            current = token
            continue

        while len(token) > max_len:
            parts.append(token[:max_len])
            token = token[max_len:]
        current = token

    if current.strip():
        parts.append(current.strip())

    return [p for p in parts if p]


def synthesize_style_bert_vits2(text: str) -> list[str]:
    chunks = split_tts_text(text)
    if not chunks:
        raise RuntimeError("読み上げる文章がまだないよ。")

    audio_urls: list[str] = []

    for chunk in chunks:
        tts_params = build_tts_params_by_mood(chunk)

        payload = {
            "text": chunk,
            "model_id": STYLE_BERT_VITS2_MODEL_ID,
            "speaker_id": STYLE_BERT_VITS2_SPEAKER_ID,
            "style": tts_params["style"],
            "style_weight": tts_params["style_weight"],
            "length": tts_params["length"],
            "noise": tts_params["noise"],
            "noisew": tts_params["noisew"],
        }

        response = requests.post(STYLE_BERT_VITS2_URL, params=payload, timeout=120)
        if response.status_code >= 400:
            raise RuntimeError(f"Style-Bert-VITS2 エラー: {response.status_code} {response.text[:200]}")

        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            data = response.json()
            if isinstance(data, dict) and data.get("audio"):
                audio_bytes = base64.b64decode(data["audio"])
            else:
                raise RuntimeError("Style-Bert-VITS2 の返り値を音声として読めなかったよ。")
        else:
            audio_bytes = response.content

        filename = f"orihime_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.wav"
        out_path = GENERATED_AUDIO_DIR / filename
        out_path.write_bytes(audio_bytes)
        audio_urls.append(f"/static/generated_audio/{filename}")

    return audio_urls


@app.route("/api/tts", methods=["POST"])
def api_tts():
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        audio_urls = synthesize_style_bert_vits2(text)
        return jsonify({"ok": True, "audio_urls": audio_urls, "text": _clean_tts_text(text)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500




@app.route("/static/<path:filename>")
def serve_static_file(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def api_status():
    t = get_time_context()
    plot = load_plot_data()
    return jsonify({
        "ok": True,
        "season": t["season"],
        "time_mode": t["time_mode"],
        "event_note": t["event_note"],
        "self_state": load_file(SELF_STATE_FILE).strip() or "",
        "work_title": plot.get("title", ""),
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        user_text = (request.form.get("message") or "").strip()
        if not user_text and "file" not in request.files and "image" not in request.files and "document" not in request.files:
            return jsonify({"ok": False, "error": "入力が空っぽみたい。"}), 400

        doc_text = ""
        image_path = None
        uploaded_filename = ""

        generic_file = request.files.get("file")
        image_file = request.files.get("image")
        doc_file = request.files.get("document")
        target_file = image_file or doc_file or generic_file

        if target_file and target_file.filename:
            uploaded_filename = Path(target_file.filename).name
            path = UPLOADS_DIR / uploaded_filename
            target_file.save(path)
            suffix = path.suffix.lower()
            if suffix in [".png", ".jpg", ".jpeg", ".webp"]:
                image_path = path
            elif suffix in [".txt", ".docx"]:
                doc_text = read_document(path)
                integrate_uploaded_document(doc_text, uploaded_filename)

        append_chat_log("user", user_text or f"[file:{uploaded_filename or 'empty'}]")
        reply = chat_with_orihime(user_text=user_text or "……", image_path=image_path, doc_text=doc_text)

        negatives = ["嫌い", "うざい", "消えろ", "最悪"]
        positives = ["ありがとう", "助かる", "好き", "嬉しい"]
        aff = load_affection()
        if any(w in user_text for w in negatives):
            aff -= 5
        elif any(w in user_text for w in positives):
            aff += 3
        else:
            aff += 1
        save_affection(aff)

        extra = maybe_memory_nudge(user_text)
        if extra:
            reply = reply + "\n\n" + extra

        append_chat_log("assistant", reply)
        maybe_add_memory_tags(user_text, reply)
        refresh_inner_state(user_text, reply)

        return jsonify({
            "ok": True,
            "reply": reply,
            "affection": load_affection(),
            "work_title": load_plot_data().get("title", ""),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/dream", methods=["POST"])
def api_dream():
    try:
        data = request.get_json(silent=True) or {}
        manual_text = (data.get("text") or request.form.get("text") or "").strip()
        summary = dream_summary(manual_text=manual_text)
        return jsonify({"ok": True, "summary": summary})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/history", methods=["GET"])
def api_history():
    try:
        return jsonify({"ok": True, "history": load_recent_logs(120)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/core", methods=["GET", "POST"])
def api_core():
    try:
        if request.method == "GET":
            return jsonify({
                "ok": True,
                "profile": load_file(PROFILE_FILE),
                "long_memory": load_file(LONG_MEMORY_FILE),
                "self_memory": load_file(SELF_MEMORY_FILE),
                "relation_memory": load_file(RELATION_FILE),
                "memory_tags": load_file(MEMORY_TAGS_FILE),
                "core": load_file(CORE_FILE),
            })
        data = request.get_json(silent=True) or {}
        if "profile" in data:
            save_file(PROFILE_FILE, data["profile"])
        if "long_memory" in data:
            save_file(LONG_MEMORY_FILE, data["long_memory"])
        if "self_memory" in data:
            save_file(SELF_MEMORY_FILE, data["self_memory"])
        if "relation_memory" in data:
            save_file(RELATION_FILE, data["relation_memory"])
        if "memory_tags" in data:
            save_file(MEMORY_TAGS_FILE, data["memory_tags"])
        if "core" in data:
            save_file(CORE_FILE, data["core"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plot", methods=["GET", "POST"])
def api_plot():
    try:
        if request.method == "GET":
            return jsonify({"ok": True, "plot": load_plot_data()})
        data = request.get_json(silent=True) or {}
        plot = save_plot_data(data)
        return jsonify({"ok": True, "plot": plot})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/memory-map", methods=["GET"])
def api_memory_map():
    try:
        return jsonify({
            "ok": True,
            "user_can_edit": [
                {"label": "プロフィール", "detail": "織姫のプロフィール、肩書き、口調のベース。"},
                {"label": "コア", "detail": "関係の核、会話ルール、壊したくない軸。"},
                {"label": "長期記憶", "detail": "固定で残したい重要事項。"},
                {"label": "思い出タグ", "detail": "自分から触れてほしい短いタグ。"},
                {"label": "小説プロット", "detail": "登場人物、舞台、期間、季節イベント、テーマ、余韻、詳細プロット。"},
            ],
            "orihime_updates": [
                {"label": "気持ち", "detail": "会話ごとに自己状態を更新。"},
                {"label": "本音", "detail": "表に出さない内側の一文。"},
                {"label": "自分メモ", "detail": "織姫自身の断片的な自己認識。"},
                {"label": "関係メモ", "detail": "ましぅとの距離感や最近の出来事。"},
                {"label": "一次メモ", "detail": "小説の進捗や次に書くことの補助メモ。"},
                {"label": "文書ダイジェスト", "detail": "アップロード文書から抽出した story / emotion / daily。"},
            ],
            "scope_text": load_file(EDITABLE_SCOPE_FILE),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/self", methods=["GET", "POST"])
def api_self():
    try:
        if request.method == "GET":
            return jsonify({"ok": True, "content": load_file(SELF_STATE_FILE).strip()})
        data = request.get_json(silent=True) or {}
        text = (data.get("content") or "").strip()
        save_file(SELF_STATE_FILE, text)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/self/refresh", methods=["POST"])
def api_self_refresh():
    try:
        logs = load_recent_logs_text(1200)
        if not logs.strip():
            return jsonify({"ok": False, "error": "まだ更新する会話がないよ。"}), 400
        refresh_inner_state("最近の流れ", logs[-400:])
        return jsonify({"ok": True, "content": load_file(SELF_STATE_FILE).strip()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/hidden", methods=["GET", "POST"])
def api_hidden():
    try:
        if request.method == "GET":
            return jsonify({"ok": True, "content": load_file(HIDDEN_FILE).strip()})
        data = request.get_json(silent=True) or {}
        text = (data.get("content") or "").strip()
        save_file(HIDDEN_FILE, text)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/write-chapter", methods=["POST"])
def api_write_chapter():
    try:
        data = write_next_chapter()
        return jsonify({"ok": True, "chapter": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/chapters", methods=["GET"])
def api_chapters():
    try:
        return jsonify({"ok": True, "chapters": list_chapters()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/chapters/<chapter_id>", methods=["GET", "POST"])
def api_chapter_detail(chapter_id: str):
    try:
        if request.method == "GET":
            return jsonify({"ok": True, "chapter": get_chapter(chapter_id)})
        data = request.get_json(silent=True) or {}
        chapter = save_chapter(
            chapter_id=chapter_id,
            title=data.get("title", ""),
            content=data.get("content", ""),
            feedback=data.get("feedback", ""),
        )
        return jsonify({"ok": True, "chapter": chapter})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/complete-work", methods=["POST"])
def api_complete_work():
    try:
        info = complete_current_work()
        return jsonify({"ok": True, **info})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



@app.route("/api/relation", methods=["GET", "POST"])
def api_relation():
    try:
        if request.method == "GET":
            return jsonify({"ok": True, "content": load_file(RELATION_FILE).strip()})
        data = request.get_json(silent=True) or {}
        save_file(RELATION_FILE, (data.get("content") or "").strip())
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plot-discussion", methods=["GET", "POST"])
def api_plot_discussion():
    try:
        if request.method == "GET":
            return jsonify({"ok": True, "content": load_file(PLOT_DISCUSSION_FILE).strip()})
        data = request.get_json(silent=True) or {}
        save_file(PLOT_DISCUSSION_FILE, (data.get("content") or "").strip())
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/current-work", methods=["GET"])
def api_current_work():
    try:
        plot = load_plot_data()
        return jsonify({
            "ok": True,
            "title": plot.get("title", ""),
            "chapters": list_chapters(),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/library", methods=["GET"])
def api_library():
    try:
        if db_enabled():
            works = db_list_archived_works()
            if works:
                return jsonify({"ok": True, "works": works})
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        works = []
        for work_dir in sorted(ARCHIVE_DIR.iterdir(), reverse=True):
            if not work_dir.is_dir():
                continue
            plot_path = work_dir / "story_plot.json"
            chapters_path = work_dir / "chapters.json"
            plot = load_json_file(plot_path, {})
            chapter_bundle = load_json_file(chapters_path, {"chapters": []})
            works.append({
                "id": work_dir.name,
                "title": plot.get("title") or work_dir.name,
                "genre": plot.get("genre", ""),
                "theme": plot.get("theme", ""),
                "chapter_count": len(chapter_bundle.get("chapters", [])),
            })
        return jsonify({"ok": True, "works": works})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/library/<work_id>", methods=["GET"])
def api_library_detail(work_id: str):
    try:
        if db_enabled():
            row = db_get_archived_work(work_id)
            if row:
                plot = row.get("plot_data") or {}
                chapter_bundle = row.get("chapters_data") or {"chapters": []}
                return jsonify({
                    "ok": True,
                    "work": {
                        "id": work_id,
                        "title": row.get("title") or plot.get("title") or work_id,
                        "genre": row.get("genre", plot.get("genre", "")),
                        "theme": row.get("theme", plot.get("theme", "")),
                        "chapters": chapter_bundle.get("chapters", []),
                    }
                })
        work_dir = ARCHIVE_DIR / work_id
        if not work_dir.exists():
            return jsonify({"ok": False, "error": "作品が見つからないよ。"}), 404
        plot = load_json_file(work_dir / "story_plot.json", {})
        chapter_bundle = load_json_file(work_dir / "chapters.json", {"chapters": []})
        return jsonify({
            "ok": True,
            "work": {
                "id": work_id,
                "title": plot.get("title") or work_id,
                "genre": plot.get("genre", ""),
                "theme": plot.get("theme", ""),
                "chapters": chapter_bundle.get("chapters", []),
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



ensure_default_files()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)