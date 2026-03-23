const API_BASE = window.location.origin;

const chatBox = document.getElementById("chat-box");
const input = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const fileInput = document.getElementById("file-input");
const cameraInput = document.getElementById("camera-input");
const statusBox = document.getElementById("status-box");
const historyBtn = document.getElementById("reload-history-btn");
const dreamBtn = document.getElementById("dream-btn");
const saveMemoryBtn = document.getElementById("save-memory-btn");
const cameraBtn = document.getElementById("camera-btn");
const fileBtn = document.getElementById("file-btn");
const menuBtn = document.getElementById("menu-btn");
const menu = document.getElementById("menu");
const dictBtn = document.getElementById("dict-btn");
const feelingBtn = document.getElementById("feeling-btn");
const hiddenBtn = document.getElementById("hidden-btn");
const historyOpenBtn = document.getElementById("history-open-btn");
const modalBackdrop = document.getElementById("modal-backdrop");
const modalContent = document.getElementById("modal-content");
const modalClose = document.getElementById("modal-close");

let currentFile = null;

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = role === "user" ? "msg user" : "msg assistant";
  div.textContent = text;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function openModal(html) {
  modalContent.innerHTML = html;
  modalBackdrop.style.display = "flex";
}

function closeModal() {
  modalBackdrop.style.display = "none";
  modalContent.innerHTML = "";
}

async function apiJson(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || "通信失敗");
  }
  return data;
}

async function loadStatus() {
  const data = await apiJson(`${API_BASE}/api/status`);
  statusBox.innerHTML = `
    <div class="status-item">好感度: ${data.affection ?? "-"}</div>
    <div class="status-item">体調: ${data.health ?? "-"}</div>
    <div class="status-item">気分: ${data.mood ?? "-"}</div>
    <div class="status-item">空腹: ${data.hunger ?? "-"}</div>
    <div class="status-item">内省: ${data.reflection ?? "-"}</div>
    <div class="status-item">状態: ${data.condition_text ?? "-"}</div>
  `;
}

async function loadHistory(toModal = false) {
  const data = await apiJson(`${API_BASE}/api/history`);
  const history = data.history || [];

  if (toModal) {
    const html = `
      <h2>会話履歴</h2>
      ${history.length ? history.map(msg => `
        <div class="history-item">
          <div class="history-role">${msg.role === "user" ? "あなた" : "織姫"}</div>
          <div>${escapeHtml(msg.content || "")}</div>
        </div>
      `).join("") : `<p class="muted">まだ履歴はないよ。</p>`}
    `;
    openModal(html);
    return;
  }

  chatBox.innerHTML = "";
  for (const msg of history) {
    addMessage(msg.role === "user" ? "user" : "assistant", msg.content || "");
  }
}

function escapeHtml(str) {
  return str
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function sendMessage() {
  const message = input.value.trim();
  if (!message && !currentFile) return;

  if (message) addMessage("user", message);
  if (currentFile) addMessage("user", `［添付: ${currentFile.name}］`);
  input.value = "";

  const formData = new FormData();
  formData.append("message", message || "");
  if (currentFile) {
    formData.append("file", currentFile);
  }

  try {
    const data = await apiJson(`${API_BASE}/api/chat`, {
      method: "POST",
      body: formData
    });
    addMessage("assistant", data.reply || "返事が空だった。");
    currentFile = null;
    fileInput.value = "";
    cameraInput.value = "";
    await loadStatus();
  } catch (e) {
    addMessage("assistant", "エラー: " + e.message);
  }
}

async function saveDream() {
  const text = prompt("夢として残したい一文を入れて。空欄なら今日の会話から自動でまとめるよ。") ?? "";
  try {
    const data = await apiJson(`${API_BASE}/api/dream`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ text })
    });
    alert("夢を保存したよ。\n\n" + data.summary);
  } catch (e) {
    alert("夢保存エラー: " + e.message);
  }
}

async function saveMemory() {
  const text = prompt("覚えさせたい内容を入れて");
  if (!text) return;
  try {
    await apiJson(`${API_BASE}/api/save-memory`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ text })
    });
    alert("記憶を保存したよ");
  } catch (e) {
    alert("記憶保存エラー: " + e.message);
  }
}

async function openHidden() {
  const data = await apiJson(`${API_BASE}/api/hidden`);
  const items = data.items || [];
  const html = `
    <h2>本音</h2>
    ${items.length ? items.map(item => `
      <div class="history-item">
        <div class="muted">${item.time || ""}</div>
        <div>${escapeHtml(item.content || "")}</div>
      </div>
    `).join("") : `<p class="muted">まだ本音はないよ。</p>`}
  `;
  openModal(html);
}

async function openFeeling() {
  const data = await apiJson(`${API_BASE}/api/self`);
  const html = `
    <h2>気持ち</h2>
    <div class="history-item">${escapeHtml(data.content || "まだ更新されてないよ。")}</div>
    <div class="bottom-row">
      <button class="small-btn" id="refresh-feeling-btn">更新</button>
    </div>
  `;
  openModal(html);
  document.getElementById("refresh-feeling-btn").onclick = async () => {
    try {
      const refreshed = await apiJson(`${API_BASE}/api/self/refresh`, { method: "POST" });
      openModal(`
        <h2>気持ち</h2>
        <div class="history-item">${escapeHtml(refreshed.content || "まだ更新されてないよ。")}</div>
        <div class="bottom-row">
          <button class="small-btn" id="refresh-feeling-btn">更新</button>
        </div>
      `);
      document.getElementById("refresh-feeling-btn").onclick = arguments.callee;
      await loadStatus();
    } catch (e) {
      alert(e.message);
    }
  };
}

async function openDict() {
  const data = await apiJson(`${API_BASE}/api/core`);
  const html = `
    <h2>辞書</h2>
    <label>プロフィール</label>
    <textarea id="dict-profile">${escapeHtml(data.profile || "")}</textarea>
    <label>コア</label>
    <textarea id="dict-core">${escapeHtml(data.core || "")}</textarea>
    <label>自分で更新する領域</label>
    <textarea id="dict-self">${escapeHtml(data.self_memory || "")}</textarea>
    <label>長期記憶</label>
    <textarea id="dict-long">${escapeHtml(data.long_memory || "")}</textarea>
    <label>思い出タグ</label>
    <textarea id="dict-tags">${escapeHtml(data.memory_tags || "")}</textarea>
    <div class="bottom-row">
      <button class="small-btn" id="save-dict-btn">保存</button>
    </div>
  `;
  openModal(html);
  document.getElementById("save-dict-btn").onclick = async () => {
    try {
      await apiJson(`${API_BASE}/api/core`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          profile: document.getElementById("dict-profile").value,
          core: document.getElementById("dict-core").value,
          self_memory: document.getElementById("dict-self").value,
          long_memory: document.getElementById("dict-long").value,
          memory_tags: document.getElementById("dict-tags").value,
        })
      });
      alert("辞書を保存したよ");
    } catch (e) {
      alert("辞書保存エラー: " + e.message);
    }
  };
}

sendBtn.addEventListener("click", sendMessage);
historyBtn.addEventListener("click", () => loadHistory(false));
dreamBtn.addEventListener("click", saveDream);
saveMemoryBtn.addEventListener("click", saveMemory);
cameraBtn.addEventListener("click", () => cameraInput.click());
fileBtn.addEventListener("click", () => {
  closeMenu();
  fileInput.click();
});
menuBtn.addEventListener("click", () => {
  menu.style.display = menu.style.display === "block" ? "none" : "block";
});
dictBtn.addEventListener("click", async () => { closeMenu(); await openDict(); });
feelingBtn.addEventListener("click", async () => { closeMenu(); await openFeeling(); });
hiddenBtn.addEventListener("click", async () => { closeMenu(); await openHidden(); });
historyOpenBtn.addEventListener("click", async () => { closeMenu(); await loadHistory(true); });
modalClose.addEventListener("click", closeModal);
modalBackdrop.addEventListener("click", (e) => { if (e.target === modalBackdrop) closeModal(); });

function closeMenu() {
  menu.style.display = "none";
}

fileInput.addEventListener("change", (e) => {
  currentFile = e.target.files[0] || null;
  if (currentFile) alert(`添付: ${currentFile.name}`);
});

cameraInput.addEventListener("change", (e) => {
  currentFile = e.target.files[0] || null;
  if (currentFile) alert(`写真を添付したよ: ${currentFile.name}`);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

loadHistory().catch(console.error);
loadStatus().catch(console.error);