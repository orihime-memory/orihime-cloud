import json
import re
from pathlib import Path


def safe_join_messages(logs: list[dict], max_chars: int = 1200) -> str:
    lines = []
    for item in logs:
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        speaker = "あなた" if role == "user" else "織姫"
        lines.append(f"{speaker}: {content}")
    text = "\n".join(lines).strip()
    return text[-max_chars:]


def split_query_words(query: str) -> list[str]:
    words = [w.strip() for w in re.split(r"[ 　、。,\n]+", str(query or "")) if w.strip()]
    return [w for w in words if len(w) >= 2]


def score_text(text: str, query_words: list[str]) -> int:
    score = 0
    for w in query_words:
        if w in text:
            score += len(w)
    return score


def simple_line_search(text: str, query: str, limit: int = 4, max_chars: int = 600) -> str:
    if not text.strip():
        return ""

    q_words = split_query_words(query)
    if not q_words:
        return ""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    scored = []

    for line in lines:
        score = score_text(line, q_words)
        if score > 0:
            scored.append((score, line))

    scored.sort(key=lambda x: x[0], reverse=True)

    picked = []
    seen = set()
    for _, line in scored:
        if line in seen:
            continue
        picked.append(line)
        seen.add(line)
        if len(picked) >= limit:
            break

    result = "\n".join(f"- {x}" for x in picked).strip()
    return result[:max_chars]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def search_file_lines(path: Path, query: str, limit: int = 4, max_chars: int = 600) -> str:
    return simple_line_search(read_text(path), query, limit=limit, max_chars=max_chars)


def search_multiple_files(paths: list[Path], query: str, per_file_limit: int = 2, total_limit: int = 6, max_chars: int = 800) -> str:
    q_words = split_query_words(query)
    if not q_words:
        return ""

    scored = []

    for path in paths:
        text = read_text(path)
        if not text:
            continue

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        local_hits = 0

        for line in lines:
            score = score_text(line, q_words)
            if score > 0:
                scored.append((score, path.name, line))
                local_hits += 1
                if local_hits >= per_file_limit:
                    break

    scored.sort(key=lambda x: x[0], reverse=True)

    picked = []
    seen = set()
    for _, fname, line in scored:
        key = (fname, line)
        if key in seen:
            continue
        picked.append(f"- [{fname}] {line}")
        seen.add(key)
        if len(picked) >= total_limit:
            break

    return "\n".join(picked)[:max_chars]


def load_recent_logs_from_txt(log_path: Path, max_lines: int = 12) -> list[dict]:
    raw = read_text(log_path)
    if not raw:
        return []

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    history = []

    for line in lines[-max_lines:]:
        if "|" not in line:
            continue
        role, text = line.split("|", 1)
        history.append({
            "role": role.strip(),
            "content": text.strip()
        })

    return history


def get_active_chapter_memory(chapters_dir: Path, limit: int = 3, max_chars: int = 700) -> str:
    items = []

    if not chapters_dir.exists():
        return ""

    for path in sorted(chapters_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            chapter_no = str(data.get("chapter_no") or "?").strip()
            title = str(data.get("title") or "無題").strip()
            summary = str(data.get("summary") or "").strip()
            if summary:
                items.append(f"- {chapter_no}章 {title}: {summary}")
            if len(items) >= limit:
                break
        except Exception:
            continue

    return "\n".join(items)[:max_chars]


def search_plot_json(plot_path: Path, query: str, max_chars: int = 700) -> str:
    if not plot_path.exists():
        return ""

    try:
        data = json.loads(plot_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    q_words = split_query_words(query)
    if not q_words:
        return ""

    scored = []

    for key, value in data.items():
        if isinstance(value, list):
            text = "\n".join(str(x) for x in value if str(x).strip())
        else:
            text = str(value or "").strip()

        if not text:
            continue

        score = score_text(text, q_words)
        if score > 0:
            scored.append((score, key, text))

    scored.sort(key=lambda x: x[0], reverse=True)

    picked = []
    for _, key, text in scored[:4]:
        compact = text.replace("\n", " / ")
        picked.append(f"- [{key}] {compact}")

    return "\n".join(picked)[:max_chars]


def chat_memory_search(user_text: str) -> str:
    base_dir = Path("memory/base")
    searchable_dir = Path("memory/searchable")
    state_dir = Path("memory/state")
    chapters_dir = Path("memory/chapters")
    plot_path = Path("memory/story_plot.json")

    log_path = searchable_dir / "logs.txt"
    hidden_path = searchable_dir / "hidden_thoughts.txt"
    self_path = searchable_dir / "self_memory.txt"
    long_path = searchable_dir / "long_memory.txt"
    digest_path = searchable_dir / "document_digests.txt"
    discussion_path = searchable_dir / "plot_discussion.txt"
    completed_path = searchable_dir / "completed_works_memory.txt"

    diary_paths = sorted(searchable_dir.glob("diary_*.txt"), reverse=True)

    sections = []

    recent_logs = load_recent_logs_from_txt(log_path, max_lines=12)
    recent_text = safe_join_messages(recent_logs, max_chars=1200)
    if recent_text:
        sections.append(f"【直近チャット】\n{recent_text}")

    hidden_hits = search_file_lines(hidden_path, user_text, limit=3, max_chars=350)
    self_hits = search_file_lines(self_path, user_text, limit=3, max_chars=350)
    inner_block = "\n".join(x for x in [hidden_hits, self_hits] if x).strip()
    if inner_block:
        sections.append(f"【内省検索】\n{inner_block}")

    long_hits = search_file_lines(long_path, user_text, limit=4, max_chars=450)
    if long_hits:
        sections.append(f"【長期記憶検索】\n{long_hits}")

    diary_hits = search_multiple_files(diary_paths, user_text, per_file_limit=2, total_limit=4, max_chars=500)
    if diary_hits:
        sections.append(f"【夢検索】\n{diary_hits}")

    chapter_hits = get_active_chapter_memory(chapters_dir, limit=3, max_chars=500)
    if chapter_hits:
        sections.append(f"【執筆中の記憶】\n{chapter_hits}")

    completed_hits = search_file_lines(completed_path, user_text, limit=3, max_chars=400)
    if completed_hits:
        sections.append(f"【図書館検索】\n{completed_hits}")

    digest_hits = search_file_lines(digest_path, user_text, limit=3, max_chars=350)
    discussion_hits = search_file_lines(discussion_path, user_text, limit=3, max_chars=350)
    plot_hits = search_plot_json(plot_path, user_text, max_chars=500)

    creative_block = "\n".join(x for x in [digest_hits, discussion_hits, plot_hits] if x).strip()
    if creative_block:
        sections.append(f"【創作記憶検索】\n{creative_block}")

    state_paths = [
        state_dir / "condition.txt",
        state_dir / "daily_rhythm.txt",
        state_dir / "hunger.txt",
        state_dir / "mood.txt",
    ]
    state_hits = search_multiple_files(state_paths, user_text, per_file_limit=1, total_limit=4, max_chars=250)
    if state_hits:
        sections.append(f"【状態検索】\n{state_hits}")

    return "\n\n".join(s for s in sections if s.strip()).strip()