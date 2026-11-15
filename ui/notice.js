"use strict";
/* Popup page for dialog.py: fills in the notice, then asks web_notice.py to
   size the window to it. Opened without pywebview (a browser preview), it
   shows a sample notice so the look can be checked on its own. */
const SAMPLE = {
  kind: "error",
  kicker: "One more step",
  title: "Your captions are ready to place again",
  message: "The captions were made, and Resolve just needs one more try to place them.",
  steps: ["Make sure the timeline is open and its subtitle tracks are unlocked.",
          "Run Workspace > Scripts > Srutilekha in DaVinci Resolve again."],
  details: "Resolve could not append the SRT to the timeline.",
  button: "Got it",
};

let api = null;

function fit() {
  if (!api) return;
  const sheet = $("sheet");
  api.fit(Math.ceil(sheet.getBoundingClientRect().height) + 2, window.devicePixelRatio || 1);
}

function render(n) {
  document.body.dataset.kind = n.kind === "info" ? "info" : "error";
  document.title = n.title || "Srutilekha";
  $("kicker").textContent = n.kicker || "";
  $("kicker").hidden = !n.kicker;
  $("title").textContent = n.title || "";
  $("message").textContent = n.message || "";
  $("message").hidden = !n.message;
  const steps = n.steps || [];
  $("stepList").replaceChildren(...steps.map((step) => {
    const li = document.createElement("li");
    li.textContent = step;
    return li;
  }));
  $("steps").hidden = !steps.length;
  $("detailsText").textContent = n.details || "";
  $("details").hidden = $("copy").hidden = !n.details;
  $("ok").textContent = n.button || "Got it";
}

function close() {
  if (api) api.close(); else window.close();
}

function wire() {
  $("ok").onclick = close;
  $("close").onclick = close;
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" || (e.key === "Enter" && !e.target.closest("summary, #copy"))) { e.preventDefault(); close(); }
  });
  document.addEventListener("contextmenu", (e) => { if (!e.target.closest("pre, .notice-message, li")) e.preventDefault(); });
  $("details").addEventListener("toggle", () => {
    $("details").querySelector("summary").textContent = $("details").open ? "Hide details" : "Show details";
    fit();
  });
  $("copy").onclick = async () => {
    try {
      await navigator.clipboard.writeText($("detailsText").textContent);
      $("copy").textContent = "Copied";
    } catch {
      if (!$("details").open) $("details").open = true;
      const range = document.createRange();
      range.selectNodeContents($("detailsText"));
      getSelection().removeAllRanges(); getSelection().addRange(range);
      UI.toast("Details selected. Press Ctrl+C to copy them.");
    }
  };
}

wire();
window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  render(await api.initial());
  await document.fonts.ready;
  requestAnimationFrame(() => { fit(); setTimeout(() => $("ok").focus(), 60); });
});
if (!window.pywebview) setTimeout(() => { if (!api) render(SAMPLE); }, 300);
