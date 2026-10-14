"use strict";
const state = { probing: false, connecting: false };
let api;

/* ── decorative waveform ─────────────────────────────────── */
(function wave() {
  const w = $("wave");
  let seed = 7;
  const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
  for (let i = 0; i < 64; i++) {
    const b = document.createElement("b");
    const env = Math.sin((i / 64) * Math.PI * 3.2) * 0.35 + 0.55;
    b.style.height = Math.max(8, Math.round((rnd() * 0.6 + 0.4) * env * 100)) + "%";
    w.appendChild(b);
  }
})();

function renderKey(hasKey) {
  $("keyBadge").textContent = hasKey ? "Saved" : "Not set";
  $("keyBadge").className = "badge " + (hasKey ? "ok" : "warn");
  $("keyState").textContent = hasKey ? "Encrypted on this PC" : "Add your API key";
}
function renderUpdate(r) {
  if (r.checking) {
    $("updateBadge").textContent = "…";
    $("updateBadge").className = "badge";
    $("updateState").textContent = "Checking GitHub releases…";
    return;
  }
  $("updateState").textContent = r.message;
  $("updateBadge").textContent = !r.ok ? "Retry" : r.available ? "v" + r.version : "Latest";
  $("updateBadge").className = "badge " + (!r.ok ? "" : r.available ? "warn" : "ok");
}
$("keyTile").onclick = () => UI.openModal("keyModal");
$("updateTile").onclick = () => UI.showUpdate();

/* ── Resolve connection ──────────────────────────────────── */
function banner(title, text, ok) {
  $("statusTitle").textContent = title;
  $("statusText").textContent = text;
  $("banner").classList.toggle("ok", !!ok);
}
async function connect() {
  if (state.connecting) return;
  state.connecting = true;
  $("connect").disabled = true;
  banner("Opening caption studio…", "Connecting to the running Resolve project.", true);
  await api.connect_resolve();
}
$("connect").onclick = connect;
$("heroCard").onclick = connect;
$("heroCard").onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") connect(); };
$("close").onclick = () => api.close();

async function probe() {
  if (state.probing || state.connecting) return;
  if (UI.modalOpen()) { setTimeout(probe, 2000); return; }
  state.probing = true;
  const r = await api.probe();
  state.probing = false;
  if (r.ready && !UI.modalOpen()) { connect(); return; }
  banner("Waiting for Resolve", r.message);
  setTimeout(probe, 2000);
}

/* ── start ───────────────────────────────────────────────── */
window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  const init = await api.initial();
  UI.init(api, { onKey: renderKey, onUpdate: renderUpdate }, init.hasKey);
  $("version").textContent = "v" + init.version;
  $("startup").checked = init.startup;
  $("startup").onchange = async (e) => {
    await api.set_startup(e.target.checked);
    UI.toast(e.target.checked ? "Srutilekha will start quietly with Windows." : "Start with Windows turned off.");
  };
  if (init.openSettings) UI.openModal("keyModal");
  UI.checkUpdates();
  if (!init.home) probe();
});
