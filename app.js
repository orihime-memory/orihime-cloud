const API_BASE = "https://orihime-cloud.onrender.com";

const chatBox = document.getElementById("chat-box");
const input = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const fileInput = document.getElementById("file-input");
const statusBox = document.getElementById("status-box");
const historyBtn = document.getElementById("reload-history-btn");
const dreamBtn = document.getElementById("dream-btn");
const saveMemoryBtn = document.getElementById("save-memory-btn");

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = role === "user" ? "msg user" : "msg assistant";
  div.textContent = text;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}

async function loadStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/status`);
    const data = await res.json();

    statusBox.innerHTML = `
      <div class="status-item">好感度: ${data.affection ?? "-"}</div>
      <div class="status-item">体調: ${data.health ?? "-"}</div>
      <div class="status-item">気分: ${data.mood ?? "-"}</div>
      <div class="status-item">空腹: ${data.hunger ?? "-"}</div>
      <div class="status-item">内省: ${data.reflection ?? "-"}</div>
      <div class="status-item">状態: ${data.condition_text ?? "-"}</div>
    `;
  } catch (e) {
    console.error("status error", e);
  }
}

async function loadHistory() {
  try {
    const res = await fetch(`${API_BASE}/api/history`);
    const data = await res.json();

    chatBox.innerHTML = "";

    for (const msg of data) {
      if (msg.role === "user") {
        addMessage("user", msg.content || "");
      } else if (msg.role === "assistant") {
        addMessage("assistant", msg.content || "");
      }
    }
  } catch (e) {
    console.error("history error", e);
  }
}

async function sendMessage() {
  const message = input.value.trim();
  const file = fileInput.files[0];

  if (!message && !file) return;

  if (message) addMessage("user", message);
  input.value = "";

  const formData = new FormData();
  formData.append("message", message || "");

  if (file) {
    formData.append("file", file);
  }

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      body: formData
    });

    const data = await res.json();

    if (!res.ok) {
      addMessage("assistant", "エラー: " + (data.detail || "送信失敗"));
      return;
    }

    addMessage("assistant", data.reply || "返事が空でした");
    fileInput.value = "";
    await loadStatus();
  } catch (e) {
    addMessage("assistant", "通信エラー: " + e.message);
  }
}

async function saveDream() {
  const text = prompt("夢として保存する文章を入れて");
  if (!text) return;

  const formData = new FormData();
  formData.append("text", text);

  try {
    const res = await fetch(`${API_BASE}/api/dream`, {
      method: "POST",
      body: formData
    });

    const data = await res.json();
    alert(data.status === "ok" ? "夢を保存したよ" : "保存失敗");
  } catch (e) {
    alert("夢保存エラー: " + e.message);
  }
}

async function saveMemory() {
  const text = prompt("覚えさせたい内容を入れて");
  if (!text) return;

  const formData = new FormData();
  formData.append("text", text);

  try {
    const res = await fetch(`${API_BASE}/api/save-memory`, {
      method: "POST",
      body: formData
    });

    const data = await res.json();
    alert(data.status === "ok" ? "記憶を保存したよ" : "保存失敗");
  } catch (e) {
    alert("記憶保存エラー: " + e.message);
  }
}

async function openHidden() {
  try {
    const res = await fetch(`${API_BASE}/api/hidden`);
    const data = await res.json();
    alert(data.map(d => d.content).join("\n\n") || "まだ本音はないよ");
  } catch (e) {
    alert("本音の取得に失敗したよ");
  }
}

async function openDict() {
  try {
    const res = await fetch(`${API_BASE}/api/core`);
    const data = await res.json();
    alert(JSON.stringify(data, null, 2));
  } catch (e) {
    alert("辞書の取得に失敗したよ");
  }
}

async function openFeeling() {
  try {
    const res = await fetch(`${API_BASE}/api/self`);
    const data = await res.json();
    alert(JSON.stringify(data, null, 2));
  } catch (e) {
    alert("気持ちの取得に失敗したよ");
  }
}

async function openStory() {
  try {
    const res = await fetch(`${API_BASE}/api/story/list`);
    const data = await res.json();
    alert(JSON.stringify(data, null, 2));
  } catch (e) {
    alert("執筆データの取得に失敗したよ");
  }
}

function openFile() {
  fileInput.click();
}

function toggleMenu() {
  const menu = document.getElementById("menu");
  menu.style.display = menu.style.display === "block" ? "none" : "block";
}

document.addEventListener("click", (e) => {
  const menu = document.getElementById("menu");
  const topActions = document.querySelector(".top-actions");
  if (!topActions.contains(e.target)) {
    menu.style.display = "none";
  }
});

sendBtn.addEventListener("click", sendMessage);

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

historyBtn.addEventListener("click", loadHistory);
dreamBtn.addEventListener("click", saveDream);
saveMemoryBtn.addEventListener("click", saveMemory);

loadHistory();
loadStatus();