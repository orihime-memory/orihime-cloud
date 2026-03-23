const API_BASE = window.location.origin;

async function sendMessage() {
  const input = document.getElementById("message");
  const msg = input.value;

  if (!msg) return;

  appendMessage("You", msg);
  input.value = "";

  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({message: msg})
  });

  const data = await res.json();
  appendMessage("織姫", data.reply);
}

function appendMessage(sender, text) {
  const chat = document.getElementById("chat");
  const div = document.createElement("div");
  div.innerText = `${sender}: ${text}`;
  chat.appendChild(div);
}

async function openHidden() {
  const res = await fetch(`${API_BASE}/api/hidden`);
  const data = await res.json();
  alert(data.map(d => d.content).join("\n\n") || "本音はまだないよ");
}

async function openFeeling() {
  const res = await fetch(`${API_BASE}/api/self`);
  const data = await res.json();
  alert(JSON.stringify(data, null, 2));
}

async function openDict() {
  const res = await fetch(`${API_BASE}/api/core`);
  const data = await res.json();
  alert(JSON.stringify(data, null, 2));
}

async function openStory() {
  const res = await fetch(`${API_BASE}/api/story/list`);
  const data = await res.json();
  alert(JSON.stringify(data, null, 2));
}

function toggleMenu() {
  const menu = document.getElementById("menu");
  menu.style.display = menu.style.display === "block" ? "none" : "block";
}