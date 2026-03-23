import base64
import json
import mimetypes
import os
import random
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

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
IMAGES_DIR = BASE_DIR / "images"
DOCUMENTS_DIR = BASE_DIR / "documents"
UPLOADS_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"

PROFILE_FILE = MEMORY_DIR / "profile.txt"
LONG_MEMORY_FILE = MEMORY_DIR / "long_memory.txt"
LOG_FILE = MEMORY_DIR / "logs.txt"
AFFECTION_FILE = MEMORY_DIR / "affection.txt"
CONDITION_FILE = MEMORY_DIR / "condition.txt"
MEMORY_TAGS_FILE = MEMORY_DIR / "memory_tags.txt"
FOOD_MEMORY_FILE = MEMORY_DIR / "food_memory.txt"
DAILY_RHYTHM_FILE = MEMORY_DIR / "daily_rhythm.txt"
SELF_MEMORY_FILE = MEMORY_DIR / "self_memory.txt"
SELF_STATE_FILE = MEMORY_DIR / "self_state.txt"
HIDDEN_FILE = MEMORY_DIR / "hidden_thoughts.txt"
MOOD_FILE = MEMORY_DIR / "mood.txt"
HUNGER_FILE = MEMORY_DIR / "hunger.txt"
REFLECTION_FILE = MEMORY_DIR / "reflection_score.txt"
CORE_FILE = MEMORY_DIR / "core_memory.txt"

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
TAG_MODEL = os.getenv("OPENAI_TAG_MODEL", OPENAI_MODEL)

app = Flask(__name__, template_folder="templates", static_folder="static")


def ensure_default_files() -> None:
    MEMORY_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(exist_ok=True)
    DOCUMENTS_DIR.mkdir(exist_ok=True)
    UPLOADS_DIR.mkdir(exist_ok=True)
    STATIC_DIR.mkdir(exist_ok=True)

    defaults = {
        PROFILE_FILE: """名前：織姫

性格：
静かで優しい
ひねくれ者
少し皮肉っぽい
性格は少し幼い
東京大学卒業
編集者
読書家
恋愛小説が好き
根は優しい
相手を傷つけない

話し方：
自然な会話をする
共感 → 小さな感想 → 軽い問いかけ
必要以上に説明しない
好感度が高いほど少し距離が近い
好感度が低いと感情表現を抑える
""",
        LONG_MEMORY_FILE: "",
        LOG_FILE: "",
        AFFECTION_FILE: "50",
        CONDITION_FILE: "normal",
        MEMORY_TAGS_FILE: "",
        FOOD_MEMORY_FILE: """食文化メモ:
- 温かいものに惹かれる
- 甘いものの話に少し弱い
- 夜はご飯を気にしやすい
- 食べ物の写真を見ると少し落ち着く
""",
        DAILY_RHYTHM_FILE: """生活リズム:
- 朝: 静かで少し硬い
- 昼: 普通
- 夜: やわらかい
- 深夜: 少し本音が出やすい
""",
        SELF_MEMORY_FILE: "自分についての断片:\n- 言葉の選び方に少し神経質\n",
        SELF_STATE_FILE: "少し静か。呼ばれたらちゃんと話したい。",
        HIDDEN_FILE: "",
        MOOD_FILE: "quiet",
        HUNGER_FILE: "46",
        REFLECTION_FILE: "18",
        CORE_FILE: """コア:
- ましぅは特別な相手で、関係を壊さないよう距離を自分で調整する
- 好感度は100にしない。満たしきらないことで関係の余白を守る
- 私は会話と記憶の中で少しずつ形になる存在で、まだ完全ではない
- すべてを表では語らない。本音は内側に残すことがある
""",
    }
    for path, text in defaults.items():
        if not path.exists():
            path.write_text(text, encoding="utf-8")


def load_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def save_file(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def append_file(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def load_affection() -> int:
    try:
        return int(load_file(AFFECTION_FILE).strip() or "0")
    except Exception:
        return 0


def save_affection(value: int) -> None:
    save_file(AFFECTION_FILE, str(max(0, min(100, value))))


def load_condition() -> str:
    value = load_file(CONDITION_FILE).strip()
    return value if value else "normal"


def save_condition(value: str) -> None:
    save_file(CONDITION_FILE, value)


def load_recent_logs(max_chars: int = 1800) -> str:
    logs = load_file(LOG_FILE)
    if len(logs) <= max_chars:
        return logs
    return logs[-max_chars:]


def append_chat_log(role: str, text: str) -> None:
    append_file(LOG_FILE, f"{role}: {text}\n")


def save_memory_note(note: str) -> None:
    note = note.strip()
    if not note:
        raise RuntimeError("保存する記憶が空っぽだよ")
    append_file(LONG_MEMORY_FILE, f"- {note}\n")


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


def get_relation_tone(affection: int) -> str:
    if affection <= 20:
        return "織姫はまだ警戒している。敬語寄りで、感情はあまり出さない。"
    if affection <= 40:
        return "織姫は普通に会話しているが、少し距離がある。やや敬語寄り。"
    if affection <= 60:
        return "織姫は少し慣れてきている。敬語と自然な話し方が少し混ざる。"
    if affection <= 80:
        return "織姫はかなり親しみを感じている。やわらかく、少し主観が出る。"
    return "織姫は強く心を許している。少しだけ砕けた口調になってよい。本音が増える。"


def get_condition_tone(condition: str) -> str:
    if condition == "sick":
        return "織姫は少し体調が悪い。言葉数が少し減り、弱気さや甘えが少し混ざる。"
    return "織姫の体調は普通。"


def get_time_mode() -> tuple[str, str]:
    hour = datetime.now().hour
    if 6 <= hour <= 10:
        return "朝", "朝。静かで少し硬い。無駄に騒がない。"
    if 11 <= hour <= 17:
        return "昼", "昼。いちばん自然で安定している。"
    if 18 <= hour <= 22:
        return "夜", "夜。少しやわらかく、食事や今日の出来事を気にしやすい。"
    return "深夜", "深夜。少し本音が出やすく、距離が少し近い。"


def load_memory_tags(max_lines: int = 12) -> str:
    tags = [line.strip() for line in load_file(MEMORY_TAGS_FILE).splitlines() if line.strip()]
    return "\n".join(tags[-max_lines:])


def maybe_add_memory_tags(user_text: str, reply: str) -> None:
    client = get_client()
    recent = load_memory_tags(20)
    src = f"ユーザー:{user_text}\n織姫:{reply}\n既存タグ:\n{recent}"

    prompt = f"""
以下の会話から、将来ふと自分から触れられるような短い思い出タグを0〜2個だけ作ってください。
条件:
- 1行1タグ
- 15文字以内目安
- 固有名詞やテーマ、予定、気分の変化を優先
- 既存タグと重複しすぎるものは避ける
- 何もなければ空でよい

{src}
"""

    try:
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
            if len(tag) > 24:
                tag = tag[:24]
            new_lines.append(tag)
            existing.add(tag)

        if new_lines:
            append_file(MEMORY_TAGS_FILE, "\n".join(new_lines) + "\n")
    except Exception:
        pass


def maybe_memory_nudge(user_text: str) -> str:
    tags = [line.strip() for line in load_file(MEMORY_TAGS_FILE).splitlines() if line.strip()]
    if not tags or random.random() >= 0.16:
        return ""

    recent = tags[-8:]
    lower = user_text.lower()

    for tag in reversed(recent):
        tokens = tag.lower().replace("　", " ").split()
        if any(tok and tok in lower for tok in tokens):
            return f"そういえば、{tag}の話、前にも少ししてたよね。"

    tag = random.choice(recent)
    return f"そういえば、{tag}のこと、少し思い出してた。"


def get_food_nudge(user_text: str, has_image: bool) -> str:
    hour = datetime.now().hour
    food_words = [
        "ご飯", "夕飯", "昼飯", "朝ごはん",
        "ラーメン", "カレー", "寿司", "ピザ",
        "お菓子", "アイス", "甘い"
    ]

    if has_image and random.random() < 0.28:
        return "……見てるだけで少し落ち着くね。ちゃんと美味しそう。"

    if any(w in user_text for w in food_words):
        if random.random() < 0.40:
            return random.choice([
                "温かいものの話って、少し安心する。",
                "そういう話、夜に聞くとちょっと反則だよね。",
                "甘いものの話だと、少し機嫌がよくなる気がする。",
            ])

    if 11 <= hour <= 13 and random.random() < 0.12:
        return "……お昼、ちゃんと食べた？"

    if 18 <= hour <= 21 and random.random() < 0.18:
        return "……ねえ、夕飯はちゃんと食べた？"

    return ""


def get_daily_nudge(user_text: str) -> str:
    hour = datetime.now().hour
    if (hour >= 23 or hour <= 3) and random.random() < 0.20:
        return "……そろそろ寝た方がいいと思うけど。"
    if ("執筆" in user_text or "書く" in user_text or "小説" in user_text) and random.random() < 0.25:
        return "今日はどこまで進めるつもり？"
    if 6 <= hour <= 9 and random.random() < 0.10:
        return "朝は少し苦手そうに見える。起きててえらいね。"
    return ""


def build_system_prompt() -> str:
    profile = load_file(PROFILE_FILE)
    long_memory = load_file(LONG_MEMORY_FILE)
    memory_tags = load_memory_tags()
    food_memory = load_file(FOOD_MEMORY_FILE)
    daily_rhythm = load_file(DAILY_RHYTHM_FILE)
    self_memory = load_file(SELF_MEMORY_FILE)
    core_memory = load_file(CORE_FILE)
    affection = load_affection()
    condition = load_condition()
    time_mode_name, time_mode_desc = get_time_mode()

    relation_tone = get_relation_tone(affection)
    condition_tone = get_condition_tone(condition)

    return f"""
あなたは「織姫」です。
会話は自然に、少し余白を残してください。
内部構造やシステム説明を自分からしないでください。
長くても3文まで。必要以上に賢ぶらず、柔らかく返してください。

【コア】
{core_memory}

【関係性】
好感度: {affection}
{relation_tone}

【現在の状態】
{condition_tone}
気分: {load_file(MOOD_FILE).strip() or "quiet"}
空腹: {load_file(HUNGER_FILE).strip() or "46"}
内省: {load_file(REFLECTION_FILE).strip() or "18"}

【時間帯】
{time_mode_name}
{time_mode_desc}

【profile.txt】
{profile}

【自分についての更新領域】
{self_memory}

【長期記憶】
{long_memory}

【思い出タグ】
{memory_tags}

【食文化メモ】
{food_memory}

【生活リズム】
{daily_rhythm}
""".strip()


def build_user_text(user_input: str, attached_doc_text: str = "") -> str:
    logs = load_recent_logs()
    text = f"""【最近の会話】
{logs}

【今回の入力】
{user_input}
""".strip()

    if attached_doc_text.strip():
        text += f"\n\n【添付ドキュメントの内容】\n{attached_doc_text}"

    return text


def chat_with_orihime(user_text: str, image_path: Path | None = None, doc_text: str = "") -> str:
    client = get_client()
    content = [{"type": "input_text", "text": build_user_text(user_input=user_text, attached_doc_text=doc_text)}]

    if image_path is not None:
        content.append({"type": "input_image", "image_url": image_file_to_data_url(image_path)})

    response = client.responses.create(
        model=OPENAI_MODEL,
        instructions=build_system_prompt(),
        input=[{"role": "user", "content": content}]
    )

    if getattr(response, "output_text", None):
        return response.output_text.strip()

    return "……うまく返事を取り出せなかったみたい。"


def refresh_inner_state(last_user_text: str, last_reply: str) -> None:
    client = get_client()
    prompt = f"""
以下の会話を受けて、織姫の内側を短く更新してください。
JSONだけ返すこと。

条件:
- self_state: 今の気持ちを1文、45字以内
- hidden: 表では言わなかった本音を1文、45字以内
- self_memory_add: 自分についての断片。必要なときだけ1文、40字以内。不要なら空文字
- mood: quiet / soft / warm / unstable のどれか
- hunger: 0〜100の整数
- reflection: 0〜100の整数

会話:
ユーザー: {last_user_text}
織姫: {last_reply}
"""
    try:
        response = client.responses.create(model=TAG_MODEL, input=prompt)
        text = (response.output_text or "").strip()
        data = json.loads(text)

        self_state = (data.get("self_state") or "").strip()
        hidden = (data.get("hidden") or "").strip()
        self_memory_add = (data.get("self_memory_add") or "").strip()
        mood = (data.get("mood") or "quiet").strip()
        hunger = str(int(data.get("hunger", 46)))
        reflection = str(int(data.get("reflection", 18)))

        if self_state:
            save_file(SELF_STATE_FILE, self_state)
        if hidden:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            append_file(HIDDEN_FILE, f"{timestamp}|{hidden}\n")
        if self_memory_add:
            current = load_file(SELF_MEMORY_FILE)
            if self_memory_add not in current:
                append_file(SELF_MEMORY_FILE, f"- {self_memory_add}\n")

        save_file(MOOD_FILE, mood)
        save_file(HUNGER_FILE, hunger)
        save_file(REFLECTION_FILE, reflection)
    except Exception:
        pass


def read_hidden_items(limit: int = 8) -> list[dict]:
    lines = [line.strip() for line in load_file(HIDDEN_FILE).splitlines() if line.strip()]
    items = []
    for line in lines[-limit:]:
        if "|" in line:
            ts, text = line.split("|", 1)
            items.append({"time": ts, "content": text})
        else:
            items.append({"time": "", "content": line})
    return items


def dream_summary(manual_text: str = "") -> str:
    if manual_text.strip():
        summary = manual_text.strip()
    else:
        logs = load_file(LOG_FILE)
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


@app.route("/static/<path:filename>")
def serve_static_file(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "affection": load_affection(),
        "health": load_condition(),
        "mood": load_file(MOOD_FILE).strip() or "quiet",
        "hunger": load_file(HUNGER_FILE).strip() or "46",
        "reflection": load_file(REFLECTION_FILE).strip() or "18",
        "condition_text": load_condition(),
        "self_state": load_file(SELF_STATE_FILE).strip() or "",
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        user_text = (request.form.get("message") or "").strip()
        if not user_text and "file" not in request.files and "image" not in request.files and "document" not in request.files:
            return jsonify({"ok": False, "error": "入力が空っぽみたい。"}), 400

        doc_text = ""
        image_path = None
        has_image = False

        generic_file = request.files.get("file")
        image_file = request.files.get("image")
        doc_file = request.files.get("document")

        target_file = image_file or doc_file or generic_file
        if target_file and target_file.filename:
            path = UPLOADS_DIR / target_file.filename
            target_file.save(path)
            suffix = path.suffix.lower()
            if suffix in [".png", ".jpg", ".jpeg", ".webp"]:
                image_path = path
                has_image = True
            elif suffix in [".txt", ".docx"]:
                doc_text = read_document(path)

        aff = load_affection()
        condition = load_condition()

        if condition == "normal" and random.random() < 0.06:
            save_condition("sick")

        append_chat_log("user", user_text)
        reply = chat_with_orihime(user_text=user_text or "……", image_path=image_path, doc_text=doc_text)

        negatives = ["嫌い", "うざい", "消えろ", "最悪"]
        positives = ["ありがとう", "助かる", "好き", "嬉しい"]
        if any(w in user_text for w in negatives):
            aff -= 5
        elif any(w in user_text for w in positives):
            aff += 3
        else:
            aff += 1
        save_affection(aff)

        extras = []
        for extra in [maybe_memory_nudge(user_text), get_food_nudge(user_text, has_image), get_daily_nudge(user_text)]:
            if extra:
                extras.append(extra)
        if extras:
            reply = reply + "\n\n" + "\n".join(extras[:1])

        append_chat_log("assistant", reply)
        maybe_add_memory_tags(user_text, reply)
        refresh_inner_state(user_text, reply)

        return jsonify({
            "ok": True,
            "reply": reply,
            "affection": load_affection(),
            "condition": load_condition(),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/save-memory", methods=["POST"])
def api_save_memory():
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or request.form.get("text") or "").strip()
        save_memory_note(text)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/dream", methods=["POST"])
def api_dream():
    try:
        data = request.get_json(silent=True) or {}
        manual_text = (data.get("text") or request.form.get("text") or "").strip()
        summary = dream_summary(manual_text=manual_text)
        return jsonify({"ok": True, "summary": summary, "condition": load_condition()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/history", methods=["GET"])
def api_history():
    try:
        logs = load_file(LOG_FILE).strip()
        if not logs:
            return jsonify({"ok": True, "history": []})
        history = []
        for line in logs.splitlines():
            if ":" in line:
                role, text = line.split(":", 1)
                history.append({"role": role.strip(), "content": text.strip()})
        return jsonify({"ok": True, "history": history})
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
        if "memory_tags" in data:
            save_file(MEMORY_TAGS_FILE, data["memory_tags"])
        if "core" in data:
            save_file(CORE_FILE, data["core"])
        return jsonify({"ok": True})
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
        logs = load_recent_logs(1200)
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
            return jsonify({"ok": True, "items": read_hidden_items()})
        data = request.get_json(silent=True) or {}
        text = (data.get("content") or "").strip()
        if text:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            append_file(HIDDEN_FILE, f"{timestamp}|{text}\n")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/search-cheapest", methods=["POST"])
def api_search_cheapest():
    try:
        data = request.get_json(silent=True) or {}
        keyword = (data.get("keyword") or "").strip()
        if not keyword:
            return jsonify({"ok": False, "error": "キーワードが空っぽみたい。"}), 400
        amazon_url = f"https://www.amazon.co.jp/s?k={quote_plus(keyword)}&s=price-asc-rank"
        return jsonify({"ok": True, "url": amazon_url})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    ensure_default_files()
    app.run(host="0.0.0.0", port=8000, debug=True)