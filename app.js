const API_BASE = window.location.origin;

let selectedFile = null;

document.addEventListener("DOMContentLoaded", async () => {
  await loadStatus();
  await loadHistory();

  const input = document.getElementById("messageInput");
  input.addEventListener("keydown", async (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      await sendMessage();
    }
  });

  document.addEventListener("click", (e) => {
    const menu = document.getElementById("menu");
    const actions = document.querySelector(".actions");
    if (!actions.contains(e.target)) {
      menu.classList.remove("show");
    }
  });
});

async function loadStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/status`);
    const data = await res.json();

    const items = [
      `好感度: ${data.affection ?? "-"}`,
      `体調: ${data.health ?? "-"}`,
      `気分: ${data.mood ?? "-"}`,
      `空腹: ${data.hunger ?? "-"}`,
      `内省: ${data.reflection ?? "-"}`,
      `状態: ${data.condition_text ?? "-"}`
    ];

    const grid = document.getElementById("statusGrid");
    grid.innerHTML = items
      .map((t) => `<div class="status-card">${escapeHtml(t)}</div>`)
      .join("");
  } catch (e) {
    console.error("status error", e);
  }
}

async function loadHistory() {
  try {
    const res = await fetch(`${API_BASE}/api/history`);
    const data = await res.json();

    const box = document.getElementById("messages");
    box.innerHTML = "";

    data.forEach((item) => {
      const role = item.role === "user" ? "user" : "assistant";
      appendMessage(role, item.content);
    });

    scrollToBottom();
  } catch (e) {
    console.error("history error", e);
  }
}

async function refreshHistory() {
  await loadHistory();
}

async function sendMessage() {
  const input = document.getElementById("messageInput");
  const text = input.value.trim();

  if (!text && !selectedFile) return;

  if (text) {
    appendMessage("user", text);
  }

  if (selectedFile) {
    appendMessage("user", `（${selectedFile.name} を送信）`);
  }

  const formData = new FormData();
  formData.append("message", text);
  if (selectedFile) {
    formData.append("file", selectedFile);
  }

  input.value = "";

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      body: formData
    });

    const data = await res.json();
    appendMessage("assistant", data.reply || "……");
  } catch (e) {
    appendMessage("assistant", "ごめん、うまく届かなかったみたい。");
    console.error("chat error", e);
  }

  selectedFile = null;
  document.getElementById("fileInput").value = "";
  scrollToBottom();
}

function appendMessage(role, text) {
  const messages = document.getElementById("messages");
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  row.appendChild(bubble);
  messages.appendChild(row);
  scrollToBottom();
}

function scrollToBottom() {
  window.scrollTo({
    top: document.body.scrollHeight,
    behavior: "smooth"
  });
}

function toggleMenu() {
  const menu = document.getElementById("menu");
  menu.classList.toggle("show");
}

function triggerFile() {
  document.getElementById("menu").classList.remove("show");
  document.getElementById("fileInput").click();
}

function handleFileSelected(event) {
  const file = event.target.files[0];
  if (!file) return;
  selectedFile = file;
}

async function saveDream() {
  const text = prompt("夢として残す短い文を入れてね");
  if (!text) return;

  const formData = new FormData();
  formData.append("text", text);

  try {
    await fetch(`${API_BASE}/api/dream`, {
      method: "POST",
      body: formData
    });
    openSimpleModal("夢保存", `<div class="note-item">夢を保存したよ。</div>`);
  } catch (e) {
    console.error("dream save error", e);
  }
}

async function saveMemory() {
  const text = prompt("記憶として残したい文を入れてね");
  if (!text) return;

  const formData = new FormData();
  formData.append("text", text);

  try {
    await fetch(`${API_BASE}/api/save-memory`, {
      method: "POST",
      body: formData
    });
    openSimpleModal("記憶保存", `<div class="note-item">記憶を保存したよ。</div>`);
  } catch (e) {
    console.error("memory save error", e);
  }
}

async function openDictionary() {
  document.getElementById("menu").classList.remove("show");

  try {
    const res = await fetch(`${API_BASE}/api/core`);
    const data = await res.json();

    const html = data.length
      ? `<div class="kv-list">${data
          .map((item) => {
            const key = mapCoreType(item.type);
            return `
              <div class="kv-item">
                <div><span class="kv-key">${escapeHtml(key)}</span>${escapeHtml(item.content || "")}</div>
              </div>
            `;
          })
          .join("")}</div>`
      : `<div class="hint">まだ辞書は空みたい。</div>`;

    openModal("辞書", html);
  } catch (e) {
    console.error("dictionary error", e);
  }
}

async function openFeeling() {
  document.getElementById("menu").classList.remove("show");

  try {
    const res = await fetch(`${API_BASE}/api/self`);
    const data = await res.json();

    const content =
      data && data.length
        ? data[0].content
        : "今はまだ、うまく言葉になっていないみたい。";

    openModal(
      "気持ち",
      `
      <div class="note-item">${escapeHtml(content)}</div>
      <div class="hint" style="margin-top: 12px;">
        気持ちは、織姫が表に出してもいいと思っている今の状態。
      </div>
      `
    );
  } catch (e) {
    console.error("feeling error", e);
  }
}

async function openHonne() {
  document.getElementById("menu").classList.remove("show");

  try {
    const res = await fetch(`${API_BASE}/api/hidden`);
    const data = await res.json();

    const html = data.length
      ? `<div class="kv-list">${data
          .map(
            (item) => `
            <div class="note-item">${escapeHtml(item.content || "")}</div>
          `
          )
          .join("")}</div>`
      : `<div class="hint">まだ本音は静かみたい。</div>`;

    openModal(
      "本音",
      `
      ${html}
      <div class="hint" style="margin-top: 12px;">
        本音は、表では言わないで胸の奥に置いてある短い言葉。
      </div>
      `
    );
  } catch (e) {
    console.error("honne error", e);
  }
}

async function openWriting() {
  document.getElementById("menu").classList.remove("show");

  try {
    const res = await fetch(`${API_BASE}/api/story/list`);
    const data = await res.json();

    const html = data.length
      ? `<div class="kv-list">${data
          .map(
            (item) => `
            <div class="story-item">
              <div><strong>${escapeHtml(item.title || "無題")}</strong></div>
            </div>
          `
          )
          .join("")}</div>`
      : `
        <div class="note-item">まだ執筆は空だよ。</div>
        <div class="hint" style="margin-top: 12px;">
          執筆はあとで「保存」と「ダウンロード」を付ける予定。
        </div>
      `;

    openModal("執筆", html);
  } catch (e) {
    console.error("writing error", e);
  }
}

function openModal(title, html) {
  document.getElementById("modalTitle").textContent = title;
  document.getElementById("modalContent").innerHTML = html;
  document.getElementById("modalBackdrop").classList.add("show");
}

function openSimpleModal(title, html) {
  openModal(title, html);
}

function closeModal(event) {
  if (event.target.id === "modalBackdrop") {
    forceCloseModal();
  }
}

function forceCloseModal() {
  document.getElementById("modalBackdrop").classList.remove("show");
}

function mapCoreType(type) {
  const map = {
    relation: "関係 / ",
    distance: "距離 / ",
    affection: "好感 / ",
    identity: "自己 / ",
    writing: "執筆 / ",
    emotion: "感情 / "
  };
  return map[type] || "記憶 / ";
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}