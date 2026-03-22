from dotenv import load_dotenv
from supabase import create_client
import os
from pathlib import Path
import re

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL が .env から読めていません")
if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY が .env から読めていません")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# txtがあるフォルダ
MEMORY_DIR = Path(r"C:\Users\coker\OneDrive\デスクトップ\memory")


def read_text(filename: str) -> str:
    path = MEMORY_DIR / filename
    if not path.exists():
        print(f"[WARN] 見つからない: {path}")
        return ""
    return path.read_text(encoding="utf-8").strip()


def read_int(filename: str, default: int = 0) -> int:
    text = read_text(filename)
    if not text:
        return default
    m = re.search(r"-?\d+", text)
    if not m:
        print(f"[WARN] 数字として読めない: {filename} -> {text}")
        return default
    return int(m.group())


def get_or_create_conversation_id() -> str:
    res = supabase.table("conversations").select("id").limit(1).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]["id"]

    created = supabase.table("conversations").insert({
        "title": "メインチャット"
    }).execute()

    if not created.data:
        raise RuntimeError("conversations の作成に失敗しました")

    return created.data[0]["id"]


def upsert_profiles():
    concept_text = read_text("concept_memory.txt")
    self_text = read_text("self_memory.txt")
    user_text = read_text("user_memory.txt")
    relation_text = read_text("relation_memory.txt")

    res = supabase.table("profiles").select("id").limit(1).execute()

    payload = {
        "name": "織姫",
        "concept_text": concept_text,
        "self_text": self_text,
        "user_text": user_text,
        "relation_text": relation_text,
    }

    if res.data and len(res.data) > 0:
        profile_id = res.data[0]["id"]
        supabase.table("profiles").update(payload).eq("id", profile_id).execute()
        print("[OK] profiles 更新")
    else:
        supabase.table("profiles").insert(payload).execute()
        print("[OK] profiles 新規作成")


def insert_status_snapshot():
    conversation_id = get_or_create_conversation_id()

    affection = read_int("affection.txt", 0)
    hunger = read_int("hunger.txt", 0)
    reflection = read_int("reflection_score.txt", 0)
    condition_text = read_text("condition.txt") or "normal"

    supabase.table("status_snapshots").insert({
        "conversation_id": conversation_id,
        "affection": affection,
        "health": 100,
        "mood": 50,
        "hunger": hunger,
        "reflection": reflection,
        "condition_text": condition_text,
    }).execute()

    print("[OK] status_snapshots 追加")


def clear_memory_items():
    supabase.table("memory_items").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    print("[OK] memory_items 初期化")


def clear_messages():
    supabase.table("messages").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    print("[OK] messages 初期化")


def clear_dreams():
    supabase.table("dreams").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    print("[OK] dreams 初期化")


def insert_memory_item(kind: str, text_value: str, importance: int = 1):
    text_value = (text_value or "").strip()
    if not text_value:
        return
    supabase.table("memory_items").insert({
        "kind": kind,
        "text_value": text_value,
        "importance": importance,
    }).execute()


def seed_memory_items():
    files = [
        ("profile.txt", "profile", 3),
        ("long_memory.txt", "long", 5),
        ("memory_tags.txt", "tag", 4),
        ("food_memory.txt", "food", 2),
        ("daily_rhythm.txt", "rhythm", 3),
        ("user_dream.txt", "user_dream", 2),
        ("orihime_dream.txt", "orihime_dream", 2),
        ("orihime_dream.txt.txt", "orihime_dream", 1),
    ]

    for filename, kind, importance in files:
        text = read_text(filename)
        if text:
            insert_memory_item(kind, text, importance)
            print(f"[OK] memory_items 追加: {filename}")


def seed_diary_to_dreams():
    conversation_id = get_or_create_conversation_id()

    diary_files = [
        "diary_2026-03-21.txt",
    ]

    for filename in diary_files:
        text = read_text(filename)
        if text:
            supabase.table("dreams").insert({
                "conversation_id": conversation_id,
                "summary_text": text,
            }).execute()
            print(f"[OK] dreams 追加: {filename}")


def parse_logs_text(log_text: str):
    """
    ゆるい解析:
    - あなた:
    - ましぅ:
    - user:
    - 織姫:
    - assistant:
    に対応
    形式が合わない部分は raw_log として memory_items に退避
    """
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    parsed = []
    raw_chunks = []

    current_role = None
    current_content = []

    def flush():
        nonlocal current_role, current_content
        if current_role and current_content:
            parsed.append({
                "role": current_role,
                "content": "\n".join(current_content).strip()
            })
        current_role = None
        current_content = []

    role_map = {
        "あなた:": "user",
        "ましぅ:": "user",
        "user:": "user",
        "織姫:": "assistant",
        "assistant:": "assistant",
    }

    for line in lines:
        matched = False
        for prefix, role in role_map.items():
            if line.startswith(prefix):
                flush()
                current_role = role
                current_content = [line[len(prefix):].strip()]
                matched = True
                break

        if matched:
            continue

        if current_role:
            current_content.append(line)
        else:
            raw_chunks.append(line)

    flush()
    return parsed, "\n".join(raw_chunks).strip()


def seed_logs():
    conversation_id = get_or_create_conversation_id()
    logs_text = read_text("logs.txt")
    if not logs_text:
        return

    parsed, raw_text = parse_logs_text(logs_text)

    if parsed:
        for msg in parsed:
            supabase.table("messages").insert({
                "conversation_id": conversation_id,
                "role": msg["role"],
                "content": msg["content"]
            }).execute()
        print(f"[OK] messages 追加: {len(parsed)}件")

    if raw_text:
        insert_memory_item("raw_log", raw_text, 2)
        print("[OK] logs.txt の未解析部分を memory_items(raw_log) に保存")


def main():
    print("=== seed start ===")
    print(f"MEMORY_DIR = {MEMORY_DIR}")

    if not MEMORY_DIR.exists():
        raise RuntimeError(f"MEMORY_DIR が見つかりません: {MEMORY_DIR}")

    upsert_profiles()
    insert_status_snapshot()

    clear_memory_items()
    seed_memory_items()

    clear_dreams()
    seed_diary_to_dreams()

    clear_messages()
    seed_logs()

    print("=== seed complete ===")


if __name__ == "__main__":
    main()