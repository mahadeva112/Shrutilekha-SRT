"use strict";
/* Master Studio form. Mirrors the Tk form's variables one to one; submit hands
   the values back to Python, which runs the existing selection/handshake path. */
let api, init;
const V = {};                       // current form values, same keys as web_studio
const PLACEHOLDER = "Select a preset", NONE = "(none saved)";
const NUMBERS = [
  ["max_chars", "Max characters", "chars", 8, 60],
  ["max_lines", "Lines per cue", "lines", 1, 4],
  ["min_secs", "Min length", "sec", 0, 4],
  ["max_secs", "Max length", "sec", 1, 12],
  ["cps", "Reading speed", "cps", 8, 30],
  ["words_per", "Max words", "0 = off", 0, 12],
];
let pending = null;                 // action waiting for an API key

/* ── small builders ──────────────────────────────────────── */
function fillSelect(sel, values, current) {
  const list = [...values];
  if (current && !list.includes(current)) list.unshift(current);
  sel.replaceChildren(...list.map((v) => new Option(v, v)));
  if (current !== undefined) sel.value = current;
}
function buildNumbers() {
  $("numGrid").replaceChildren(...NUMBERS.map(([key, label, unit, lo, hi]) => {
    const wrap = document.createElement("label");
    wrap.className = "fld";
    wrap.innerHTML = `<span>${label}</span><div class="num" data-num="${key}"><input data-key="${key}" inputmode="decimal" spellcheck="false"><span class="unit">${unit}</span><span class="rail"><em></em></span></div>`;
    wrap.querySelector(".num").dataset.range = lo + "," + hi;
    return wrap;
  }));
}
function moveThumb(seg) {
  const active = seg.querySelector("button.active");
  const thumb = seg.querySelector(".seg-thumb");
  if (!active || !thumb) return;
  thumb.style.width = active.offsetWidth + "px";
  thumb.style.transform = `translateX(${active.offsetLeft - 4}px)`;
}

/* ── value plumbing ──────────────────────────────────────── */
const frame = () => init.frames[V.aspect] || init.frames.Reel;
function set(key, value, quiet) {
  V[key] = value;
  if (!quiet) render();
}

function bindControls() {
  document.querySelectorAll("[data-key]").forEach((el) => {
    const key = el.dataset.key;
    if (el.type === "checkbox") el.onchange = () => set(key, el.checked ? 1 : 0);
    else if (el.tagName === "SELECT") el.onchange = () => set(key, el.value);
    else el.oninput = () => set(key, el.value);
  });
  document.querySelectorAll("#taskSeg button").forEach((b) => b.onclick = () => set("task", b.dataset.task));
  document.querySelectorAll("[data-browse]").forEach((b) => b.onclick = async (e) => {
    e.preventDefault();
    const path = await api.pick_file(b.dataset.browse);
    if (path) set(b.dataset.browse === "script" ? "ref_script" : "sync_srt", path);
  });

  window.addEventListener("resize", () => document.querySelectorAll(".segments").forEach(moveThumb));
}

/* ── render ──────────────────────────────────────────────── */
function render() {
  document.querySelectorAll("[data-key]").forEach((el) => {
    const v = V[el.dataset.key];
    if (el.type === "checkbox") el.checked = !!Number(v);
    else if (el.tagName === "SELECT") { if (v && ![...el.options].some((o) => o.value === v)) el.add(new Option(v, v), 0); el.value = v; }
    else if (document.activeElement !== el) el.value = v ?? "";
  });
  const sync = V.task === "Sync Existing";
  document.querySelectorAll("#taskSeg button").forEach((b) => b.classList.toggle("active", b.dataset.task === V.task));
  document.querySelectorAll(".segments").forEach(moveThumb);
  $("syncField").querySelectorAll("input, button").forEach((el) => el.disabled = !sync);
  $("goText").textContent = sync ? "Sync timing" : "Generate captions";
  $("pageLead").textContent = sync ? "Keep your words. Rebuild the timing from the audio." : "Your audio. Clear, readable captions.";

  document.querySelectorAll("[data-num]").forEach((box) => {
    const [lo, hi] = box.dataset.range.split(",").map(Number);
    const n = parseFloat(String(V[box.dataset.num] ?? "").trim());
    box.querySelector("em").style.width = (Number.isFinite(n) ? Math.max(0, Math.min(1, (n - lo) / (hi - lo))) * 100 : 0) + "%";
    box.classList.toggle("bad", String(V[box.dataset.num] ?? "").trim() !== "" && !Number.isFinite(n));
  });
  renderComfort();
  renderSummary();
}

function renderComfort() {
  const cps = parseFloat(V.cps);
  let verdict = "—", col = "var(--dim)", frac = 0;
  if (Number.isFinite(cps)) {
    frac = Math.min(1, Math.max(0, cps) / 40);
    [verdict, col] = cps <= 0 ? ["No limit", "var(--muted)"] : cps <= 17 ? ["Very relaxed", "var(--green)"]
      : cps <= 25 ? ["Comfortable", "var(--green)"] : cps <= 32 ? ["Brisk", "var(--gold)"] : ["Too fast", "var(--red)"];
  }
  $("comfortVerdict").textContent = verdict;
  $("comfortVerdict").style.color = col;
  $("comfortBar").style.width = frac * 100 + "%";
  $("comfortBar").style.background = col;
}

/* The review screen's preview of the selected cue. Resolve's scripting API
   cannot style subtitle cues, so it draws Resolve's own default look at the
   timeline's frame, rather than a font or position that would never arrive. */
function fitFrame(box, f, padW, padH) {
  // Largest frame of the timeline's aspect inside the box.
  const w = box.clientWidth - padW, h = box.clientHeight - padH, aspect = frame().aspect;
  let fw = w, fh = w / aspect;
  if (fh > h) { fh = h; fw = h * aspect; }
  f.style.width = Math.max(40, fw) + "px";
  f.style.height = Math.max(40, fh) + "px";
  const portrait = aspect < 1;
  f.classList.toggle("reel", portrait);
  f.classList.toggle("hd", !portrait);
}

function paintCaption(f, cap, text) {
  // The cue at the frame's default caption height, in plain white.
  cap.textContent = text;
  cap.style.bottom = frame().srt_posy * 100 + "%";
  const fh = parseFloat(f.style.height) || 300, fw = parseFloat(f.style.width) || 170;
  const tlH = (init.timelineRes && init.timelineRes[1]) || 1080;
  // Enlarged for legibility, as the Tk illustration was.
  cap.style.fontSize = Math.max(10, Math.min(fw * 0.085, fh * (55 / tlH) * 1.6)) + "px";
  cap.style.color = "#fff";
  cap.style.textShadow = "0 2px 6px #000c";
}

function renderSummary() {
  const base = (p) => p.split(/[\\/]/).pop();
  const bits = [];
  if (V.task === "Sync Existing") {
    const srt = String(V.sync_srt || "").trim();
    bits.push(srt ? `Re-time ${base(srt)} against ${V.chosen}` : `Choose the SRT to re-time against ${V.chosen}`);
  } else bits.push(`${V.chosen} · ${V.lang} → a subtitle track`);
  bits.push(Number(V.review) ? "review first" : "applied straight away");
  $("summary").textContent = bits.join("  ·  ");
}

/* ── presets ─────────────────────────────────────────────── */
function fillPresets(list, pick) {
  fillSelect($("presetSel"), [PLACEHOLDER, ...(list.length ? list : [NONE])], pick || PLACEHOLDER);
  $("presetSel").options[0].disabled = true;
}
function wirePresets() {
  $("presetSel").onchange = async (e) => {
    const name = e.target.value;
    if (name === PLACEHOLDER || name === NONE) return;
    const r = await api.load_preset(name);
    if (!r.ok) { UI.toast(r.message, "err"); return; }
    Object.assign(V, r.values);
    render();
    UI.toast(`Preset “${name}” applied`);
  };
  $("savePreset").onclick = () => UI.busy($("savePreset"), async () => {
    const typed = $("presetName").value.trim();
    const picked = $("presetSel").value;
    const name = typed || (picked !== PLACEHOLDER && picked !== NONE ? picked : "");
    if (!name) { $("presetName").focus(); UI.toast("Type a name for the preset first."); return; }
    const r = await api.save_preset(name, V);
    if (!r.ok) { UI.toast(r.message, "err"); return; }
    fillPresets(r.presets, name);
    $("presetName").value = "";
    UI.toast(`Preset “${name}” saved`);
  });
  $("removePreset").onclick = () => UI.busy($("removePreset"), async () => {
    const name = $("presetSel").value;
    if (name === PLACEHOLDER || name === NONE) return;
    const r = await api.remove_preset(name);
    if (!r.ok) { UI.toast(r.message, "err"); return; }
    fillPresets(r.presets);
    UI.toast(`Preset “${name}” removed`);
  });
  $("presetName").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.stopPropagation(); $("savePreset").click(); } });
}

/* ── submit ──────────────────────────────────────────────── */
async function submit(action) {
  const buttons = [$("goBtn"), $("undoBtn"), $("cancelBtn")];
  buttons.forEach((b) => b.disabled = true);
  const go = action !== "undo";
  if (go) { $("goBtn").classList.add("working"); $("goText").textContent = "Starting…"; }
  const r = await api.submit(action, { ...V });
  if (r.ok && r.running) { Run.enter(); return; }
  if (r.ok) return;                                   // window is closing
  buttons.forEach((b) => b.disabled = false);
  $("goBtn").classList.remove("working");
  render();
  if (r.needKey) { pending = action; UI.openModal("keyModal"); }
  UI.toast(r.message, r.needKey ? "" : "err");
}
const primaryAction = () => (V.task === "Sync Existing" ? "sync" : "generate");

function wireActions() {
  $("goBtn").onclick = () => submit(primaryAction());
  $("undoBtn").onclick = () => submit("undo");
  $("cancelBtn").onclick = () => api.cancel();
  $("close").onclick = () => (Run.phase === "done" ? api.close_done() : api.cancel());
  $("runCancel").onclick = () => { $("runCancel").disabled = true; api.cancel(); };
  $("doneClose").onclick = () => api.close_done();
  $("versionPill").onclick = () => (UI.state.update ? UI.showUpdate() : UI.checkUpdates());
  document.addEventListener("keydown", (e) => {
    if (UI.modalOpen() || e.defaultPrevented) return;
    if (Run.phase === "done") { if (e.key === "Enter" || e.key === "Escape") api.close_done(); return; }
    if (Run.phase) return;                            // no shortcuts while a job runs
    const tag = document.activeElement?.tagName;
    if (e.key === "Escape") api.cancel();
    else if (e.key === "Enter" && tag !== "SELECT" && tag !== "BUTTON" && tag !== "TEXTAREA") submit(primaryAction());
  });
}

function renderUpdate(r) {
  const pill = $("versionPill");
  if (r.checking) { pill.textContent = "Checking…"; pill.className = "pill"; return; }
  pill.className = "pill" + (r.available ? " warn" : "");
  pill.textContent = r.available ? "Update v" + r.version : "v" + (init.version || r.version || "");
  pill.title = r.message || "Check for updates";
}

/* ── progress and done ───────────────────────────────────── */
const Run = {
  phase: null, target: 0, shown: 0, timer: null, stagesKey: "",

  enter() {
    this.phase = "progress";
    $("formView").hidden = true;
    $("runView").hidden = false;
    $("runView").classList.add("entering");
    this.poll();
    this.timer = setInterval(() => this.poll(), 200);
    requestAnimationFrame(() => this.animate());
  },

  resume() {
    // Back from review: the same progress card, now for the import.
    this.phase = "progress";
    this.shown = 0;
    $("runView").hidden = false;
    $("progressCard").hidden = false;
    $("runCancel").disabled = false;
    this.timer = setInterval(() => this.poll(), 200);
    requestAnimationFrame(() => this.animate());
  },

  async poll() {
    const s = await api.run_state();
    if (!s || this.phase === "done" || this.phase === "review") return;
    if (s.phase === "review") {
      this.phase = "review";
      clearInterval(this.timer);
      Review.enter();
      return;
    }
    $("runTitle").textContent = s.title || "Working";
    $("runKicker").textContent = s.title === "Undoing" ? "UNDO" : V.task === "Sync Existing" ? "SYNC" : "CAPTIONS";
    $("runMsg").textContent = s.msg || "";
    $("runElapsed").textContent = fmtTime(s.elapsed);
    this.target = s.pct;
    this.stages(s.stages || [], s.pct);
    if (s.phase === "done") this.done(s);
  },

  animate() {
    // Ease the visible bar toward the reported percentage, as the Tk bar did.
    if (this.phase !== "progress") return;
    const gap = this.target - this.shown;
    this.shown = gap > 0 ? Math.min(this.target, this.shown + Math.max(0.25, gap * 0.12)) : this.target;
    $("runBar").style.width = this.shown + "%";
    $("runPct").textContent = Math.round(this.shown) + "%";
    requestAnimationFrame(() => this.animate());
  },

  stages(list, pct) {
    const key = list.map((x) => x[0]).join("|");
    if (key !== this.stagesKey) {
      this.stagesKey = key;
      $("runStages").replaceChildren(...list.map(([name]) => {
        const li = document.createElement("li");
        li.innerHTML = `<span></span><em></em>`;
        li.firstChild.textContent = name;
        return li;
      }));
    }
    [...$("runStages").children].forEach((li, i) => {
      const start = list[i][1], end = i + 1 < list.length ? list[i + 1][1] : 100;
      const state = pct >= end ? "done" : pct >= start ? "now" : "todo";
      li.className = state;
      li.querySelector("em").textContent = state === "now" ? "running" : "";
    });
  },

  done(s) {
    this.phase = "done";
    clearInterval(this.timer);
    $("progressCard").hidden = true;
    $("doneCard").hidden = false;
    $("doneMark").classList.toggle("failed", !!s.failed);
    $("doneTitle").textContent = s.failed ? "Couldn't start captions" : "Done";
    const lines = String(s.message || "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    $("doneHeadline").textContent = lines[0] || "Done.";
    const body = [], meta = [];
    let saved = false;
    for (const ln of lines.slice(1)) {
      if (ln.replace(/\.$/, "").toLowerCase() === "project saved") { saved = true; continue; }
      const kv = doneMeta(ln);
      if (kv) meta.push(kv); else body.push(ln);
    }
    $("doneBody").replaceChildren(...body.map((ln) => {
      const li = document.createElement("li");
      const low = ln.toLowerCase();
      if (low.includes("could not") || low.includes("unavailable") || low.includes("never reported")) li.className = "warn";
      if (ln.startsWith("(")) li.className = "detail";
      li.textContent = ln;
      return li;
    }));
    const dl = $("doneMeta");
    dl.replaceChildren();
    for (const [label, value] of meta) {
      const dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = label; dd.textContent = value;
      dl.append(dt, dd);
    }
    if (saved) dl.insertAdjacentHTML("beforeend", `<div class="saved">${UI.icon("check")}Project saved</div>`);
    $("doneElapsed").textContent = (s.failed ? "Stopped after " : "Finished in ") + fmtTime(s.elapsed_final ?? s.elapsed);
    setTimeout(() => $("doneClose").focus(), 300);
  },
};

function doneMeta(line) {
  // "Label: value" rows from Resolve's report, as App._done_meta reads them.
  const i = line.indexOf(":");
  if (i < 0) return null;
  const label = line.slice(0, i).trim(), value = line.slice(i + 1).trim();
  if (!label || !value || label.length > 18 || value.length > 80 || !/^\p{L}/u.test(label)) return null;
  if (/[.,;()]/.test(label)) return null;
  return [label, value];
}
function fmtTime(sec) {
  sec = Math.max(0, Math.round(Number(sec) || 0));
  return sec < 60 ? sec + "s" : Math.floor(sec / 60) + "m " + String(sec % 60).padStart(2, "0") + "s";
}

/* ── start ───────────────────────────────────────────────── */
window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  init = await api.initial();
  Object.assign(V, init.values);
  UI.init(api, {
    onUpdate: renderUpdate,
    onKeyClosed: (hasKey) => { if (pending && hasKey) { const a = pending; pending = null; submit(a); } else pending = null; },
  }, init.hasKey);
  $("crumb").textContent = init.crumb ? "·  " + init.crumb : "";
  $("versionPill").textContent = "v" + init.version;
  buildNumbers();
  fillSelect($("trackSel"), init.items.length ? init.items : [""], V.chosen);
  fillSelect($("langSel"), init.languages, V.lang);
  fillPresets(init.presets);
  UI.hydrateIcons();
  bindControls();
  wirePresets();
  wireActions();
  render();
  document.body.classList.add("ready");
  if (init.needsKey && !init.hasKey) UI.openModal("keyModal");
  UI.checkUpdates();
});
