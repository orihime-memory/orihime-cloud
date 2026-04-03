
const API_BASE = window.location.origin;

const input = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const fileInput = document.getElementById("file-input");
const cameraInput = document.getElementById("camera-input");
const imageInput = document.getElementById("image-input");
const plusBtn = document.getElementById("plus-btn");
const menu = document.getElementById("menu");
const fileBtn = document.getElementById("file-btn");
const plotBtn = document.getElementById("plot-btn");
const currentWorkBtn = document.getElementById("current-work-btn");
const writeBtn = document.getElementById("write-btn");
const completeBtn = document.getElementById("complete-btn");
const libraryBtn = document.getElementById("library-btn");
const feelingBtn = document.getElementById("feeling-btn");
const hiddenBtn = document.getElementById("hidden-btn");
const relationBtn = document.getElementById("relation-btn");
const discussionBtn = document.getElementById("discussion-btn");
const historyIconBtn = document.getElementById("history-icon-btn");
const cameraBtn = document.getElementById("camera-btn");
const micBtn = document.getElementById("mic-btn");
const speakerWrap = document.getElementById("speaker-wrap");
const speakerLabel = document.getElementById("speaker-label");
const modalBackdrop = document.getElementById("modal-backdrop");
const modalContent = document.getElementById("modal-content");
const modalClose = document.getElementById("modal-close");
const ttsAudio = document.getElementById("tts-audio");
const presenceText = document.getElementById("presence-text");
const workTitle = document.getElementById("work-title");
const messageText = document.getElementById("message-text");
const messageState = document.getElementById("message-state");
const orihimeImage = document.getElementById("orihime-image");

let currentFile = null;
let micEnabled = false;
let speakerEnabled = false;
let imageObjectUrl = null;

function escapeHtml(str) {
  return String(str || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
function nl2br(str) {
  return escapeHtml(str).replaceAll("\n", "<br>");
}
function openModal(html) {
  modalContent.innerHTML = html;
  modalBackdrop.style.display = "flex";
}
function closeModal() {
  modalBackdrop.style.display = "none";
  modalContent.innerHTML = "";
}
function closeMenu() {
  menu.style.display = "none";
}
async function apiJson(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || "通信失敗");
  return data;
}
function setLatestMessage(text, state = "最新の返答") {
  messageText.textContent = text || "";
  messageState.textContent = state;
}
function setSpeakerState(active, label = "") {
  speakerEnabled = active;
  speakerWrap.classList.toggle("active", active);
  speakerLabel.textContent = label || (active ? "スピーカー再生中" : "スピーカーOFF");
}
async function loadStatus() {
  const data = await apiJson(`${API_BASE}/api/status`);
  presenceText.textContent = data.self_state || "待機中";
  workTitle.textContent = data.work_title || "未設定";
}
async function speakText(text) {
  const data = await apiJson(`${API_BASE}/api/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text })
  });
  const url = (data.audio_urls || [])[0];
  if (!url) return;
  ttsAudio.src = url;
  setSpeakerState(true, "スピーカー再生中");
  await ttsAudio.play();
}
ttsAudio.addEventListener("ended", () => setSpeakerState(false, "スピーカーOFF"));

async function sendMessage() {
  const message = input.value.trim();
  if (!message && !currentFile) return;

  presenceText.textContent = "応答中";
  setLatestMessage("……考えてる。", "応答中");

  const formData = new FormData();
  formData.append("message", message || "");
  if (currentFile) formData.append("file", currentFile);

  input.value = "";

  try {
    const data = await apiJson(`${API_BASE}/api/chat`, { method: "POST", body: formData });
    setLatestMessage(data.reply || "返事が空だった。", "最新の返答");
    currentFile = null;
    fileInput.value = "";
    cameraInput.value = "";
    await loadStatus();
    try { await speakText(data.reply || ""); } catch (_) {}
  } catch (e) {
    setLatestMessage("エラー: " + e.message, "エラー");
    presenceText.textContent = "待機中";
  }
}

async function openHistory() {
  const data = await apiJson(`${API_BASE}/api/history`);
  const history = data.history || [];
  openModal(`
    <h2>会話履歴</h2>
    ${history.length ? history.map(msg => `
      <div class="history-item">
        <div class="history-role">${msg.role === "user" ? "あなた" : "織姫"}</div>
        <div>${nl2br(msg.content || "")}</div>
      </div>`).join("") : `<p>まだ履歴はないよ。</p>`}
  `);
}

async function openFeeling() {
  const data = await apiJson(`${API_BASE}/api/self`);
  openModal(`
    <h2>気持ち</h2>
    <textarea id="feeling-text">${escapeHtml(data.content || "")}</textarea>
    <div class="bottom-row">
      <button class="small-btn" id="save-feeling-btn">保存</button>
      <button class="small-btn" id="refresh-feeling-btn">更新</button>
    </div>
  `);
  document.getElementById("save-feeling-btn").onclick = async () => {
    await apiJson(`${API_BASE}/api/self`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ content: document.getElementById("feeling-text").value })
    });
    await loadStatus();
  };
  document.getElementById("refresh-feeling-btn").onclick = async () => {
    const refreshed = await apiJson(`${API_BASE}/api/self/refresh`, { method: "POST" });
    document.getElementById("feeling-text").value = refreshed.content || "";
    await loadStatus();
  };
}

async function openHidden() {
  const data = await apiJson(`${API_BASE}/api/hidden`);
  openModal(`
    <h2>本音</h2>
    <textarea id="hidden-text">${escapeHtml(data.content || "")}</textarea>
    <div class="bottom-row"><button class="small-btn" id="save-hidden-btn">保存</button></div>
  `);
  document.getElementById("save-hidden-btn").onclick = async () => {
    await apiJson(`${API_BASE}/api/hidden`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ content: document.getElementById("hidden-text").value })
    });
  };
}

async function openRelation() {
  const data = await apiJson(`${API_BASE}/api/relation`);
  openModal(`
    <h2>関係</h2>
    <textarea id="relation-text">${escapeHtml(data.content || "")}</textarea>
    <div class="bottom-row"><button class="small-btn" id="save-relation-btn">保存</button></div>
  `);
  document.getElementById("save-relation-btn").onclick = async () => {
    await apiJson(`${API_BASE}/api/relation`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ content: document.getElementById("relation-text").value })
    });
  };
}

async function openDiscussion() {
  const data = await apiJson(`${API_BASE}/api/plot-discussion`);
  openModal(`
    <h2>プロット相談</h2>
    <textarea id="discussion-text">${escapeHtml(data.content || "")}</textarea>
    <div class="bottom-row"><button class="small-btn" id="save-discussion-btn">保存</button></div>
  `);
  document.getElementById("save-discussion-btn").onclick = async () => {
    await apiJson(`${API_BASE}/api/plot-discussion`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ content: document.getElementById("discussion-text").value })
    });
  };
}

async function openPlot() {
  const data = await apiJson(`${API_BASE}/api/plot`);
  const plot = data.plot || {};
  const field = (id, label, value) => `<label>${label}</label><textarea id="${id}">${escapeHtml(value || "")}</textarea>`;
  openModal(`
    <h2>固定プロット</h2>
    ${field("plot-title", "タイトル", plot.title)}
    ${field("plot-genre", "ジャンル", plot.genre)}
    ${field("plot-theme", "テーマ", plot.theme)}
    ${field("plot-characters", "登場人物", plot.characters)}
    ${field("plot-locations", "場所", plot.locations)}
    ${field("plot-detail", "本筋の骨格", plot.detailed_plot)}
    ${field("plot-story", "story", plot.story_layer)}
    ${field("plot-emotion", "emotion", plot.emotion_layer)}
    ${field("plot-daily", "daily", plot.daily_layer)}
    ${field("plot-scratch", "一次メモ", plot.scratchpad)}
    ${field("plot-next", "次に書くこと", plot.next_step)}
    ${field("plot-pending", "保留点", plot.pending_points)}
    <div class="bottom-row"><button class="small-btn" id="save-plot-btn">保存</button></div>
  `);
  document.getElementById("save-plot-btn").onclick = async () => {
    await apiJson(`${API_BASE}/api/plot`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        title: document.getElementById("plot-title").value,
        genre: document.getElementById("plot-genre").value,
        theme: document.getElementById("plot-theme").value,
        characters: document.getElementById("plot-characters").value,
        locations: document.getElementById("plot-locations").value,
        detailed_plot: document.getElementById("plot-detail").value,
        story_layer: document.getElementById("plot-story").value,
        emotion_layer: document.getElementById("plot-emotion").value,
        daily_layer: document.getElementById("plot-daily").value,
        scratchpad: document.getElementById("plot-scratch").value,
        next_step: document.getElementById("plot-next").value,
        pending_points: document.getElementById("plot-pending").value
      })
    });
    await loadStatus();
  };
}

async function openCurrentWork() {
  const data = await apiJson(`${API_BASE}/api/current-work`);
  const chapters = data.chapters || [];
  openModal(`
    <h2>執筆中の作品</h2>
    <p class="muted">タイトル: ${escapeHtml(data.title || "未設定")}</p>
    ${chapters.length ? chapters.map(c => `
      <div class="chapter-card">
        <div class="history-role">${escapeHtml((c.chapter_no || "?") + "章 " + (c.title || "無題"))}</div>
        <div>${nl2br(c.summary || "")}</div>
        <div class="bottom-row"><button class="small-btn" data-open-chapter="${escapeHtml(c.id)}">開く</button></div>
      </div>`).join("") : `<p>まだ章はないよ。</p>`}
  `);
  document.querySelectorAll("[data-open-chapter]").forEach(btn => {
    btn.onclick = () => openChapter(btn.getAttribute("data-open-chapter"));
  });
}

async function openChapter(chapterId) {
  const data = await apiJson(`${API_BASE}/api/chapters/${chapterId}`);
  const ch = data.chapter || {};
  openModal(`
    <h2>${escapeHtml((ch.chapter_no || "?") + "章 " + (ch.title || "無題"))}</h2>
    <label>タイトル</label>
    <textarea id="chapter-title">${escapeHtml(ch.title || "")}</textarea>
    <label>本文</label>
    <textarea id="chapter-content" style="min-height:260px;">${escapeHtml(ch.content || "")}</textarea>
    <label>フィードバック</label>
    <textarea id="chapter-feedback">${escapeHtml(ch.feedback || "")}</textarea>
    <div class="bottom-row">
      <button class="small-btn" id="save-chapter-btn">保存</button>
    </div>
  `);
  document.getElementById("save-chapter-btn").onclick = async () => {
    await apiJson(`${API_BASE}/api/chapters/${chapterId}`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        title: document.getElementById("chapter-title").value,
        content: document.getElementById("chapter-content").value,
        feedback: document.getElementById("chapter-feedback").value
      })
    });
    openCurrentWork();
  };
}

async function openLibrary() {
  const data = await apiJson(`${API_BASE}/api/library`);
  const works = data.works || [];
  openModal(`
    <h2>図書館</h2>
    ${works.length ? works.map(w => `
      <div class="work-card">
        <div class="history-role">${escapeHtml(w.title || w.id)}</div>
        <div class="muted">${escapeHtml(w.genre || "")} / ${escapeHtml(w.theme || "")}</div>
        <div class="muted">章数: ${w.chapter_count || 0}</div>
        <div class="bottom-row"><button class="small-btn" data-open-work="${escapeHtml(w.id)}">中身を見る</button></div>
      </div>`).join("") : `<p>まだ図書館には作品がないよ。</p>`}
  `);
  document.querySelectorAll("[data-open-work]").forEach(btn => {
    btn.onclick = () => openLibraryWork(btn.getAttribute("data-open-work"));
  });
}

async function openLibraryWork(workId) {
  const data = await apiJson(`${API_BASE}/api/library/${workId}`);
  const work = data.work || {};
  const chapters = work.chapters || [];
  openModal(`
    <h2>${escapeHtml(work.title || work.id || "作品")}</h2>
    <div class="muted">${escapeHtml(work.genre || "")}</div>
    <div class="muted" style="margin-top:4px;">${escapeHtml(work.theme || "")}</div>
    <h3>章</h3>
    ${chapters.length ? chapters.map(ch => `
      <div class="chapter-card">
        <div class="history-role">${escapeHtml((ch.chapter_no || "?") + "章 " + (ch.title || "無題"))}</div>
        <div>${nl2br(ch.summary || "")}</div>
        <details style="margin-top:8px;"><summary>本文を見る</summary><div style="margin-top:8px; white-space:pre-wrap;">${escapeHtml(ch.content || "")}</div></details>
      </div>`).join("") : `<p>章はまだないよ。</p>`}
  `);
}

async function writeChapter() {
  const data = await apiJson(`${API_BASE}/api/write-chapter`, { method: "POST" });
  const ch = data.chapter || {};
  setLatestMessage(ch.content || "章を書いたよ。", ch.title || "新しい章");
}

async function completeWork() {
  await apiJson(`${API_BASE}/api/complete-work`, { method: "POST" });
  await loadStatus();
  setLatestMessage("作品を図書館へ移したよ。", "完結");
}

plusBtn.onclick = (e) => {
  e.stopPropagation();
  menu.style.display = menu.style.display === "block" ? "block" : "block";
  if (menu.dataset.open === "1") {
    menu.style.display = "none";
    menu.dataset.open = "0";
  } else {
    menu.style.display = "block";
    menu.dataset.open = "1";
  }
};
historyIconBtn.onclick = openHistory;
fileBtn.onclick = () => { closeMenu(); fileInput.click(); };
plotBtn.onclick = () => { closeMenu(); openPlot(); };
currentWorkBtn.onclick = () => { closeMenu(); openCurrentWork(); };
writeBtn.onclick = () => { closeMenu(); writeChapter(); };
completeBtn.onclick = () => { closeMenu(); completeWork(); };
libraryBtn.onclick = () => { closeMenu(); openLibrary(); };
feelingBtn.onclick = () => { closeMenu(); openFeeling(); };
hiddenBtn.onclick = () => { closeMenu(); openHidden(); };
relationBtn.onclick = () => { closeMenu(); openRelation(); };
discussionBtn.onclick = () => { closeMenu(); openDiscussion(); };
modalClose.onclick = closeModal;
modalBackdrop.onclick = (e) => { if (e.target === modalBackdrop) closeModal(); };
document.addEventListener("click", (e) => {
  if (!menu.contains(e.target) && e.target !== plusBtn) {
    closeMenu();
    menu.dataset.open = "0";
  }
});

sendBtn.onclick = sendMessage;
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

cameraBtn.onclick = () => {
  cameraBtn.classList.toggle("recording");
  currentFile = null;
  cameraInput.click();
};
micBtn.onclick = () => {
  micEnabled = !micEnabled;
  micBtn.classList.toggle("active", micEnabled);
  presenceText.textContent = micEnabled ? "音声待機中" : "待機中";
};
speakerWrap.onclick = () => setSpeakerState(!speakerEnabled);

fileInput.onchange = (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  currentFile = file;
  setLatestMessage(`［添付: ${file.name}］`, "ファイル選択");
};
cameraInput.onchange = (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  currentFile = file;
  setLatestMessage(`［撮影画像: ${file.name}］`, "カメラ");
  cameraBtn.classList.remove("recording");
};
imageInput.onchange = (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  if (imageObjectUrl) URL.revokeObjectURL(imageObjectUrl);
  imageObjectUrl = URL.createObjectURL(file);
  orihimeImage.src = imageObjectUrl;
};

window.addEventListener("load", async () => {
  await loadStatus();
});
