"use strict";
/* Review & split. Mirrors the Tk review editor: the page owns the cue cards
   and live statistics; Python owns every structural change (re-cut, split,
   merge, delete) so the cues match what the Tk editor would produce. */
const Review = {
  rows: [], s: null, colors: {}, fields: [], recipes: [], sel: -1,
  filter: "all", ver: 0, timer: null, busy: false,

  async enter() {
    $("runView").hidden = true;
    $("reviewView").hidden = false;
    $("reviewView").classList.add("entering");
    const r = await api.review_init({ ...V });
    if (!r) { UI.toast("The transcript could not be opened for review.", "err"); return; }
    Object.assign(this, { colors: r.colors, fields: r.fields, recipes: r.recipes });
    this.buildControls();
    this.rebuild(r.segs, r.s);
    new ResizeObserver(() => { this.rows.forEach((r) => this.fit(r)); this.paintPreview(); }).observe($("cueList"));
  },

  /* ── split controls ─────────────────────────────────────── */
  fmt(f, v) { return f === "%d" ? String(Math.trunc(Number(v))) : Number(v).toFixed(1); },

  buildControls() {
    $("recipes").replaceChildren(...this.recipes.map(([name, vals]) => {
      const b = document.createElement("button");
      b.className = "chip";
      b.textContent = name;
      b.onclick = () => {
        this.fields.forEach(([, key, , , , f], i) => { V[key] = this.fmt(f, vals[i]); });
        this.syncControls();
        this.schedule();
      };
      return b;
    }));
    $("splitFields").replaceChildren(...this.fields.map(([label, key, lo, hi, step, f]) => {
      const row = document.createElement("label");
      row.className = "split-field";
      row.innerHTML = `<span></span><input type="text" inputmode="decimal" spellcheck="false"><input type="range">`;
      row.firstChild.textContent = label;
      const [box, range] = row.querySelectorAll("input");
      Object.assign(range, { min: lo, max: hi, step });
      box.dataset.key = range.dataset.key = key;
      box.oninput = () => { V[key] = box.value; this.syncControls(box); this.schedule(); };
      range.oninput = () => { V[key] = this.fmt(f, range.value); this.syncControls(range); this.schedule(); };
      return row;
    }));
    const chips = [["all", "All"], ["issue", "Needs attention"], ["edited", "Edited"]];
    $("filterChips").replaceChildren(...chips.map(([key, label]) => {
      const b = document.createElement("button");
      b.className = "chip" + (key === "issue" ? " warn" : "") + (key === this.filter ? " on" : "");
      b.dataset.filter = key;
      b.dataset.label = label;
      b.onclick = () => { this.filter = key; this.applyFilter(); };
      return b;
    }));
    $("cueSearch").oninput = () => this.applyFilter();
    $("inspSplit").onclick = () => this.splitAtCaret(this.sel, false);
    $("inspMerge").onclick = () => { if (this.sel > 0) this.edit("merge", this.sel - 1, 0, this.sel - 1); };
    $("applyBtn").onclick = () => this.apply();
    $("reviewCancel").onclick = () => api.cancel();
    this.syncControls();
  },

  syncControls(skip) {
    document.querySelectorAll(".split-field input").forEach((el) => {
      if (el === skip) return;
      const v = V[el.dataset.key];
      if (el.type === "range") {
        const n = parseFloat(v);
        if (Number.isFinite(n)) el.value = n;
        const pct = (el.value - el.min) / (el.max - el.min) * 100;
        el.style.setProperty("--fill", pct + "%");
      } else el.value = v ?? "";
    });
    if (skip && skip.type === "range") skip.style.setProperty("--fill", (skip.value - skip.min) / (skip.max - skip.min) * 100 + "%");
    // Light the recipe actually in force, none once values drift from all three.
    [...$("recipes").children].forEach((chip, i) => {
      const vals = this.recipes[i][1];
      chip.classList.toggle("on", this.fields.every(([, key, , , , f], j) => String(V[key] ?? "").trim() === this.fmt(f, vals[j])));
    });
  },

  /* ── re-cut (debounced, like the Tk editor's 220 ms) ────── */
  schedule() {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.resplit(), 220);
  },

  async resplit() {
    this.timer = null;
    const ver = this.ver;
    const r = await api.review_resplit(this.live(), { ...V });
    if (ver !== this.ver) { this.schedule(); return false; }      // typed meanwhile: cut again
    if (!r.ok) { $("cueStatus").textContent = r.message; return false; }
    this.rebuild(r.segs, r.s);
    return true;
  },

  live() { return this.rows.map((row) => ({ ...row.seg, text: row.ta.value })); },

  async edit(op, i, nLeft, select, focusStart) {
    if (this.busy) return;
    this.busy = true;
    try {
      const r = await api.review_edit(op, i, this.live(), nLeft || 0);
      if (!r.ok) return;
      this.rebuild(r.segs, this.s, Math.max(0, Math.min(select, r.segs.length - 1)));
      if (focusStart && this.rows[select]) {
        const ta = this.rows[select].ta;
        ta.focus();
        ta.setSelectionRange(0, 0);
      }
    } finally { this.busy = false; }
  },

  splitAtCaret(i, focusRight) {
    const row = this.rows[i];
    if (!row) return;
    const nLeft = row.ta.value.slice(0, row.ta.selectionStart).split(/\s+/).filter(Boolean).length;
    this.edit("split", i, nLeft, focusRight ? i + 1 : i, focusRight);
  },

  /* ── cue cards ──────────────────────────────────────────── */
  rebuild(segs, s, select) {
    this.s = s;
    this.rows = segs.map((seg, i) => this.card(seg, i, i === segs.length - 1));
    $("cueList").replaceChildren(...this.rows.map((r) => r.el));
    this.rows.forEach((r) => this.fit(r));
    if (!this.rows.length) $("cueList").innerHTML = `<div class="empty">Every cue was deleted. Change a split value to cut the transcript again, or Cancel.</div>`;
    $("cueStatus").textContent = `${segs.length} cues · ${s.max_chars}×${s.max_lines} · ${s.cps > 0 ? "CPS ≤ " + s.cps : "CPS off"}`;
    $("applyText").textContent = segs.length ? `Apply ${segs.length} captions` : "Apply captions";
    this.sel = -1;
    this.counts();
    this.applyFilter(select);
  },

  card(seg, i, last) {
    const el = document.createElement("div");
    el.className = "cue";
    el.innerHTML = `<span class="stripe"></span><div><div class="cue-top"><span class="idx"></span><span class="tc"></span><span class="over"></span>
      <span class="cue-acts"><button data-act="split" title="Split this cue where the caret is (Enter)">Split</button>${last ? "" : `<button data-act="merge" title="Merge this cue into the next (Ctrl+M)">Merge</button>`}<button data-act="delete" class="del" title="Delete this cue (Ctrl+Delete)">Delete</button></span></div>
      <textarea spellcheck="false"></textarea></div><div class="meter"><span></span><i><em></em></i></div>`;
    const color = this.colors[String(seg.spk || 0)];
    if (color) el.querySelector(".stripe").style.background = color;
    el.querySelector(".idx").textContent = String(i + 1).padStart(2, "0");
    el.querySelector(".tc").textContent = `${short(seg.s)} → ${short(seg.e)}`;
    const ta = el.querySelector("textarea");
    ta.value = seg.text;
    ta.rows = Math.max(1, this.s.max_lines);
    const row = { seg, orig: seg.text, el, ta, i };
    ta.addEventListener("focus", () => this.select(row.i));
    el.addEventListener("mousedown", () => this.select(row.i));
    ta.addEventListener("input", () => { this.ver++; this.refreshRow(row); });
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); this.splitAtCaret(row.i, true); }
      else if (e.ctrlKey && (e.key === "m" || e.key === "M")) { e.preventDefault(); if (!last) this.edit("merge", row.i, 0, row.i); }
      else if (e.ctrlKey && e.key === "Delete") { e.preventDefault(); this.edit("delete", row.i, 0, row.i); }
    });
    el.querySelectorAll("[data-act]").forEach((b) => b.onclick = (e) => {
      e.stopPropagation();
      const act = b.dataset.act;
      if (act === "split") this.splitAtCaret(row.i, false);
      else this.edit(act, row.i, 0, row.i);
    });
    this.refreshRow(row, true);
    return row;
  },

  stats(row) {
    // App._cue_stats: measured from the text a viewer reads.
    const text = row.ta.value, lines = text.split("\n").length;
    const cps = text.replace(/\n/g, "").length / Math.max(0.001, row.seg.e - row.seg.s);
    return { cps, lines, chars: text.replace(/\n/g, "").length,
             overCps: this.s.cps > 0 && cps > this.s.cps, overLines: lines > this.s.max_lines };
  },

  refreshRow(row, quiet) {
    const st = this.stats(row);
    const [frac, col] = grade(st.cps, this.s.cps);
    const meter = row.el.querySelector(".meter");
    meter.firstElementChild.textContent = Math.round(st.cps) + " cps";
    meter.firstElementChild.style.color = col;
    meter.querySelector("em").style.width = frac * 100 + "%";
    meter.querySelector("em").style.background = col;
    row.el.querySelector(".over").textContent = st.overLines ? `▲ ${st.lines} lines` : "";
    const was = row.issue;
    row.issue = st.overCps || st.overLines;
    row.el.classList.toggle("issue", row.issue);
    if (row.el.isConnected) this.fit(row);
    if (quiet) return;
    this.counts();
    if (was !== row.issue && this.filter === "issue") this.applyFilter();
    if (row.i === this.sel) { this.inspect(); this.paintPreview(); }
  },

  fit(row) {
    // Grow the text box to its content; it has no height until it is on the page.
    row.ta.style.height = "auto";
    row.ta.style.height = row.ta.scrollHeight + "px";
  },

  counts() {
    const n = { all: this.rows.length, issue: this.rows.filter((r) => r.issue).length,
                edited: this.rows.filter((r) => r.ta.value !== r.orig).length };
    $("filterChips").querySelectorAll(".chip").forEach((c) => {
      c.textContent = `${c.dataset.label} ${n[c.dataset.filter]}`;
      c.classList.toggle("on", c.dataset.filter === this.filter);
    });
    $("reviewSummary").textContent = `${V.lang} · ${n.all} cues` + (n.issue ? ` · ${n.issue} need attention` : "") + (n.edited ? ` · ${n.edited} edited` : "");
  },

  matches(row) {
    if (this.filter === "issue" && !row.issue) return false;
    if (this.filter === "edited" && row.ta.value === row.orig) return false;
    const q = $("cueSearch").value.trim().toLowerCase();
    return !q || row.ta.value.toLowerCase().includes(q);
  },

  applyFilter(select) {
    let first = -1;
    this.rows.forEach((r, i) => { r.i = i; const on = this.matches(r); r.el.hidden = !on; if (on && first < 0) first = i; });
    this.counts();
    // A selection the filter just hid would leave the inspector describing a
    // cue that is not on screen.
    const want = select !== undefined && this.rows[select] && !this.rows[select].el.hidden ? select
               : this.sel >= 0 && this.rows[this.sel] && !this.rows[this.sel].el.hidden ? this.sel : first;
    this.select(want, true);
  },

  select(i, force) {
    if (i === this.sel && !force) return;
    this.rows.forEach((r) => r.el.classList.remove("sel"));
    this.sel = i;
    if (this.rows[i]) this.rows[i].el.classList.add("sel");
    this.inspect();
    this.paintPreview();
  },

  /* ── inspector and preview ──────────────────────────────── */
  inspect() {
    const row = this.rows[this.sel], dl = $("insp");
    $("inspMerge").disabled = !(this.sel > 0);
    $("inspSplit").disabled = !row;
    if (!row) { $("inspTitle").textContent = "No cue selected"; dl.replaceChildren(); return; }
    $("inspTitle").textContent = "Cue " + String(this.sel + 1).padStart(2, "0");
    const st = this.stats(row), s = this.s, budget = Math.max(1, s.max_chars * s.max_lines);
    const [frac, col] = grade(st.cps, s.cps);
    const items = [
      ["In", short(row.seg.s)], ["Out", short(row.seg.e)],
      ["Duration", Math.max(0, row.seg.e - row.seg.s).toFixed(2) + " s"],
      ["Characters", `${st.chars} / ${budget}`, st.chars > budget ? "var(--gold)" : "", Math.min(1, st.chars / budget)],
      ["Reading speed", Math.round(st.cps) + " cps", col, frac],
      ["Lines", `${st.lines} / ${s.max_lines}`, st.overLines ? "var(--red)" : ""],
    ];
    dl.replaceChildren();
    for (const [label, value, colour, bar] of items) {
      const dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = label; dd.textContent = value;
      if (colour) dd.style.color = colour;
      dl.append(dt, dd);
      if (bar !== undefined) {
        const b = document.createElement("div");
        b.className = "bar";
        b.innerHTML = `<em style="width:${bar * 100}%;background:${colour || "var(--green)"}"></em>`;
        dl.append(b);
      }
    }
  },

  paintPreview() {
    const row = this.rows[this.sel];
    fitFrame($("miniViewport"), $("miniFrame"), 16, 16);
    paintCaption($("miniFrame"), $("miniCap"), row ? row.ta.value.split(/\s+/).join(" ").trim() : "");
  },

  /* ── apply ──────────────────────────────────────────────── */
  async apply() {
    $("applyBtn").disabled = true;
    try {
      if (this.timer) { clearTimeout(this.timer); if (!(await this.resplit())) return; }
      const r = await api.review_apply(this.live());
      if (!r.ok) { UI.toast(r.message, "err"); return; }
      $("reviewView").hidden = true;
      Run.resume();
    } finally { $("applyBtn").disabled = false; }
  },
};

function short(sec) {
  // App._fmt_short: m:ss.ss
  sec = Math.max(0, sec);
  const m = Math.floor(sec / 60), s = sec - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
}

function grade(cps, limit) {
  // CueMeter.grade: fraction of the limit, and its colour.
  if (!limit || limit <= 0) return [0, "var(--muted)"];
  if (cps > limit) return [1, "var(--red)"];
  const frac = Math.min(1, cps / limit);
  return [frac, frac >= 0.8 ? "var(--gold)" : "var(--green)"];
}
