"use strict";
/* Shared helpers for every Srutilekha WebView2 window: icons, toasts, modals,
   the API-key dialog and the update dialog. Pages call UI.init(api, hooks). */
const $ = (id) => document.getElementById(id);

const UI = (() => {
  const ICONS = {
    key: '<circle cx="8" cy="9" r="5"/><path d="m12 12 8 8m-4-4 3-3m-6 0 3-3"/>',
    min: '<path d="M6 12h12"/>',
    max: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    x: '<path d="m6 6 12 12M18 6 6 18"/>',
    arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-14.6-4.5L4 8m0-4v4h4M4 13a8 8 0 0 0 14.6 4.5L20 16m0 4v-4h-4"/>',
    power: '<path d="M12 3v8m5.7-4.7a8 8 0 1 1-11.4 0"/>',
    eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    wave: '<path d="M3 12h2m3-5v10m4-13v16m4-11v6m4-3h1"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6m-6 4h4"/>',
    bookmark: '<path d="M6 4h12v17l-6-4-6 4z"/>',
    type: '<path d="M5 6V4h14v2M12 4v16m-3 0h6"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    sparkle: '<path d="M12 3v4m0 10v4M3 12h4m10 0h4M6 6l2.5 2.5m7 7L18 18M6 18l2.5-2.5m7-7L18 6"/>',
  };
  const icon = (name) => `<svg viewBox="0 0 24 24">${ICONS[name] || ""}</svg>`;
  function hydrateIcons(root = document) {
    root.querySelectorAll("[data-icon]").forEach((el) => {
      el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon));
      el.removeAttribute("data-icon");
    });
  }

  function toast(text, kind) {
    const t = $("toast");
    t.textContent = text;
    t.className = "toast show" + (kind ? " " + kind : "");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => t.classList.remove("show"), kind === "err" ? 4200 : 2600);
  }
  function setStatus(el, text, kind) {
    el.textContent = text || "";
    el.className = "status-line" + (kind ? " " + kind : "");
  }
  const modalOpen = () => [...document.querySelectorAll(".scrim")].some((m) => !m.hidden);
  function openModal(id) {
    const m = $(id);
    m.classList.remove("leaving");
    m.hidden = false;
    const first = m.querySelector("input, .btn.primary");
    if (first) setTimeout(() => first.focus(), 60);
  }
  function closeModal(m) {
    if (typeof m === "string") m = $(m);
    if (!m || m.hidden || m.classList.contains("leaving")) return;
    m.classList.add("leaving");
    setTimeout(() => { m.hidden = true; m.classList.remove("leaving"); }, 160);
    if (m.onclose) m.onclose();
  }
  async function busy(button, work) {
    button.disabled = true;
    try { return await work(); } finally { button.disabled = false; }
  }

  const MODALS = `
<div class="scrim" id="keyModal" hidden>
  <div class="modal" role="dialog" aria-labelledby="keyTitle">
    <button class="icon-btn modal-x" data-close data-icon="x" title="Close"></button>
    <span class="kicker">SETTINGS / CONNECTION</span>
    <h2 id="keyTitle">Account connection</h2>
    <p class="muted">Set up the voice behind your captions. Your key is encrypted for this Windows account and only sent to ElevenLabs.</p>
    <label class="field-label" for="keyInput">ElevenLabs API key</label>
    <div class="field">
      <span class="lead" data-icon="lock"></span>
      <input id="keyInput" type="password" autocomplete="off" spellcheck="false">
      <button class="icon-btn" id="reveal" title="Show" data-icon="eye"></button>
    </div>
    <div class="status-line" id="keyStatus"></div>
    <div class="modal-actions">
      <button class="btn ghost danger" id="removeKey">Remove saved key</button>
      <span class="grow"></span>
      <button class="btn" id="testKey">Test connection</button>
      <button class="btn primary" id="saveKey">Save key</button>
    </div>
  </div>
</div>
<div class="scrim" id="updateModal" hidden>
  <div class="modal" role="dialog" aria-labelledby="updTitle">
    <button class="icon-btn modal-x" data-close data-icon="x" title="Close"></button>
    <span class="kicker" id="updDate">NEW RELEASE</span>
    <h2 id="updTitle">Install update</h2>
    <ul class="notes" id="updNotes"></ul>
    <p class="muted">Close all Srutilekha windows before continuing in Setup. Your API key and presets are kept.</p>
    <div class="progress" id="updProgress" hidden><i></i></div>
    <div class="status-line" id="updStatus"></div>
    <div class="modal-actions">
      <span class="grow"></span>
      <button class="btn" data-close>Later</button>
      <button class="btn primary" id="installUpdate">Install update</button>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>`;

  const state = { hasKey: false, update: null };
  let api, hooks = {};

  function renderKey() {
    $("removeKey").hidden = !state.hasKey;
    $("keyInput").placeholder = state.hasKey
      ? "Saved key in use · paste a new key to replace it"
      : "Paste your ElevenLabs API key";
    if (hooks.onKey) hooks.onKey(state.hasKey);
  }

  function wireKeyModal() {
    $("keyModal").onclose = () => {
      $("keyInput").value = "";
      $("keyInput").type = "password";
      setStatus($("keyStatus"), "");
      if (hooks.onKeyClosed) hooks.onKeyClosed(state.hasKey);
    };
    $("reveal").onclick = () => {
      const i = $("keyInput");
      i.type = i.type === "password" ? "text" : "password";
      i.focus();
    };
    $("testKey").onclick = () => busy($("testKey"), async () => {
      setStatus($("keyStatus"), "Checking connection…", "busy");
      const r = await api.test_key($("keyInput").value);
      setStatus($("keyStatus"), r.message, r.ok ? "ok" : "err");
    });
    $("saveKey").onclick = () => busy($("saveKey"), async () => {
      const value = $("keyInput").value.trim();
      if (!value) {
        if (state.hasKey) { closeModal("keyModal"); return; }
        setStatus($("keyStatus"), "Paste your API key first.", "err");
        $("keyInput").focus();
        return;
      }
      const r = await api.save_key(value);
      if (!r.ok) { setStatus($("keyStatus"), r.message, "err"); return; }
      state.hasKey = true;
      renderKey();
      closeModal("keyModal");
      toast(r.message);
    });
    $("removeKey").onclick = () => busy($("removeKey"), async () => {
      const r = await api.remove_key();
      setStatus($("keyStatus"), r.message, r.ok ? "" : "err");
      if (r.ok) { state.hasKey = false; renderKey(); }
    });
    $("keyInput").addEventListener("keydown", (e) => { if (e.key === "Enter") $("saveKey").click(); });
  }

  async function checkUpdates() {
    if (hooks.onUpdate) hooks.onUpdate({ checking: true });
    const r = await api.check_updates();
    state.update = r.available ? r : null;
    if (hooks.onUpdate) hooks.onUpdate(r);
    return r;
  }
  function showUpdate() {
    const u = state.update;
    if (!u) { checkUpdates(); return; }
    $("updTitle").textContent = "Install v" + u.version;
    $("updDate").textContent = u.released ? "RELEASED " + u.released : "NEW RELEASE";
    const list = $("updNotes");
    list.replaceChildren(...u.notes.filter((n) => n.trim()).map((n) => {
      const li = document.createElement("li");
      li.textContent = n.replace(/^[-*#\s]+/, "");
      return li;
    }));
    list.hidden = !list.children.length;
    openModal("updateModal");
  }
  function wireUpdateModal() {
    $("installUpdate").onclick = () => busy($("installUpdate"), async () => {
      $("updProgress").hidden = false;
      setStatus($("updStatus"), "Downloading update…", "busy");
      const r = await api.install_update();
      if (!r.ok) {
        $("updProgress").hidden = true;
        setStatus($("updStatus"), r.message, "err");
      }
    });
  }

  function wireChrome() {
    const on = (id, fn) => { if ($(id)) $(id).onclick = fn; };
    on("minimize", () => api.minimize());
    on("maximize", () => api.toggle_maximize());
    on("openKey", () => openModal("keyModal"));
    document.querySelectorAll("[data-close]").forEach((b) => b.onclick = () => closeModal(b.closest(".scrim")));
    document.querySelectorAll(".scrim").forEach((s) => s.addEventListener("mousedown", (e) => { if (e.target === s) closeModal(s); }));
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      const open = [...document.querySelectorAll(".scrim")].find((m) => !m.hidden);
      if (open) { closeModal(open); e.stopImmediatePropagation(); }
    }, true);
    document.addEventListener("contextmenu", (e) => { if (!e.target.closest("input, textarea, .notes")) e.preventDefault(); });
  }

  document.body.insertAdjacentHTML("beforeend", MODALS);
  hydrateIcons();

  return {
    icon, hydrateIcons, toast, setStatus, openModal, closeModal, modalOpen, busy,
    checkUpdates, showUpdate, state,
    get api() { return api; },
    init(pageApi, pageHooks, hasKey) {
      api = pageApi;
      hooks = pageHooks || {};
      state.hasKey = !!hasKey;
      wireKeyModal();
      wireUpdateModal();
      wireChrome();
      renderKey();
    },
  };
})();
