const $ = (id) => document.getElementById(id);

const state = {
  model: null,
  file: null,
};

function getApiBase() {
  return $("apiBase").value.trim().replace(/\/$/, "");
}

function setNotice(text, isError = false) {
  const el = $("sideNotice");
  el.textContent = text || "";
  el.className = "tiny " + (isError ? "err" : "ok");
}

function escapeHtml(str) {
  return (str || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderMessage(role, content, meta = "") {
  const box = $("messages");
  const div = document.createElement("div");
  div.className = `msg ${role === "user" ? "user" : "assistant"}`;
  div.innerHTML = `<div>${escapeHtml(content)}</div>${meta ? `<div class="meta">${escapeHtml(meta)}</div>` : ""}`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function clearMessages() {
  $("messages").innerHTML = "";
}

async function loadStatus() {
  const base = getApiBase();
  $("apiLabel").textContent = base;

  const res = await fetch(`${base}/api/status`);
  if (!res.ok) throw new Error("status の取得に失敗");
  const data = await res.json();

  $("affection").textContent = data.affection ?? "-";
  $("health").textContent = data.health ?? "-";
  $("mood").textContent = data.mood ?? "-";
  $("hunger").textContent = data.hunger ?? "-";
  $("reflection").textContent = data.reflection ?? "-";
  $("condition").textContent = data.condition_text ?? "-";
}

async function loadHistory() {
  const base = getApiBase();
  const res = await fetch(`${base}/api/history`);
  if (!res.ok) throw new Error("history の取得に失敗");
  const data = await res.json();

  clearMessages();
  for (const msg of data) {
    const role = msg.role === "user" ? "user" : "assistant";
    renderMessage(role, msg.content || "");
  }
}

async function sendMessage() {
  const base = getApiBase();
  const text = $("messageInput").value.trim();
  if (!text) return;

  const file = $("fileInput").files[0] || null;
  state.file = file;

  renderMessage("user", text, file ? `添付: ${file.name}` : "");
  $("messageInput").value = "";

  const formData = new FormData();
  formData.append("message", text);

  if (file) {
    formData.append("file", file);
    formData.append("file_type", file.type || "unknown");
  }

  const res = await fetch(`${base}/api/chat`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    let errText = "送信に失敗";
    try {
      const err = await res.json();
      errText = err.detail || JSON.stringify(err);
    } catch {
      errText = await res.text();
    }
    renderMessage("assistant", `エラー: ${errText}`);
    return;
  }

  const data = await res.json();
  state.model = data.model || null;
  renderMessage("assistant", data.reply || "", state.model ? `model: ${state.model}` : "");
  await loadStatus().catch(() => {});
}

async function saveMemory() {
  const base = getApiBase();
  const text = $("memoryText").value.trim();
  if (!text) return;

  const fd = new FormData();
  fd.append("text", text);

  const res = await fetch(`${base}/api/save-memory`, { method: "POST", body: fd });
  if (!res.ok) throw new Error("メモ保存に失敗");
  $("memoryText").value = "";
  setNotice("メモを保存したよ。");
}

async function saveDream() {
  const base = getApiBase();
  const text = $("dreamText").value.trim();
  if (!text) return;

  const fd = new FormData();
  fd.append("text", text);

  const res = await fetch(`${base}/api/dream`, { method: "POST", body: fd });
  if (!res.ok) throw new Error("夢保存に失敗");
  $("dreamText").value = "";
  setNotice("夢を保存したよ。");
}

function bindPreview() {
  $("fileInput").addEventListener("change", () => {
    const file = $("fileInput").files[0];
    const box = $("previewBox");
    box.innerHTML = "";

    if (!file) return;

    const info = document.createElement("div");
    info.textContent = `選択中: ${file.name} (${file.type || "unknown"})`;
    box.appendChild(info);

    if (file.type && file.type.startsWith("image/")) {
      const img = document.createElement("img");
      img.className = "preview";
      img.src = URL.createObjectURL(file);
      box.appendChild(img);
    }
  });
}

async function boot() {
  try {
    await loadStatus();
    await loadHistory();
    setNotice("接続できたよ。");
  } catch (e) {
    setNotice(`起動時エラー: ${e.message}`, true);
  }
}

$("sendBtn").addEventListener("click", () => {
  sendMessage().catch((e) => {
    setNotice(e.message, true);
  });
});

$("reloadBtn").addEventListener("click", () => {
  boot();
});

$("saveMemoryBtn").addEventListener("click", () => {
  saveMemory().catch((e) => setNotice(e.message, true));
});

$("saveDreamBtn").addEventListener("click", () => {
  saveDream().catch((e) => setNotice(e.message, true));
});

$("messageInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage().catch((err) => setNotice(err.message, true));
  }
});

bindPreview();
boot();
