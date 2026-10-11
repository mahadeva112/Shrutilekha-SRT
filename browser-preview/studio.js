const $ = id => document.getElementById(id);
const samples = {
  Bengali: ['তোমার গল্প,\nতোমার ভাষায়।', 'ছোট ছোট মুহূর্তেই\nলুকিয়ে থাকে জীবন।', 'প্রতিটি শব্দ\nএকটা নতুন শুরু।'],
  Hindi: ['आपकी कहानी,\nआपकी भाषा।', 'छोटे पलों में\nछिपी है ज़िंदगी।', 'हर शब्द,\nएक नई शुरुआत।'],
  English: ['Your story.\nYour own words.', 'A little moment.\nA lasting memory.', 'Every word,\na new beginning.']
};
let mode = 'generate', activeCue = 0, playing = null, busy = false, accent = '#ffe5a0';
let presets = Object.create(null);
try {
  const saved = JSON.parse(localStorage.getItem('srutilekha-studio-presets') || '{}');
  if (saved && typeof saved === 'object' && !Array.isArray(saved)) Object.assign(presets, saved);
} catch {}
const fields = ['track','language','chars','lines','minSecs','maxSecs','font','size','height','punct','speakers','review','safezone','outline','shadow'];
const captionSamples = () => samples[$('language').value] || samples.English;
function status(text) {
  $('status').replaceChildren(document.createTextNode(text));
  const note = document.createElement('small');
  note.textContent = 'Mock UI · sample data · no transcription or Resolve connection';
  $('status').append(note);
}
function preview() {
  $('caption').textContent = captionSamples()[activeCue];
  $('caption').style.bottom = $('height').value + '%';
  $('caption').style.fontSize = (Number($('size').value) * ($('screen').classList.contains('hd') ? .85 : .56)) + 'px';
  $('caption').style.fontFamily = $('font').value;
  $('caption').style.color = accent;
  $('caption').style.webkitTextStroke = $('outline').checked ? '.5px #172321' : '0';
  $('caption').style.textShadow = $('shadow').checked ? '0 2px 10px #000c' : 'none';
  $('heightValue').textContent = $('height').value + '%';
  $('sizeValue').textContent = $('size').value;
  $('safe').hidden = !$('safezone').checked;
  const dense = Number($('chars').value) > 35;
  $('comfort').textContent = dense ? 'A little more to read' : 'Easy to read';
  $('comfortDetail').textContent = `${$('chars').value} characters · up to ${$('lines').value} lines`;
}
function seek() {
  const position = Number($('scrub').value);
  activeCue = Math.min(2, Math.floor(position / 8));
  $('time').textContent = `00:00:${String(Math.floor(position)).padStart(2,'0')}:${String(Math.floor((position % 1) * 24)).padStart(2,'0')}`;
  $('wavePlayhead').style.left = (12 + position / 24 * 84) + '%';
  preview();
}
function stopPlaying() { clearInterval(playing); playing = null; $('play').textContent = '▶'; $('play').setAttribute('aria-label','Play sample caption preview'); }
$('play').onclick = () => {
  if (playing) return stopPlaying();
  if (Number($('scrub').value) >= 24) $('scrub').value = 0;
  $('play').textContent = 'Ⅱ'; $('play').setAttribute('aria-label','Pause sample caption preview');
  playing = setInterval(() => { $('scrub').value = Math.min(24, Number($('scrub').value) + .1); seek(); if (Number($('scrub').value) >= 24) stopPlaying(); }, 100);
};
$('scrub').oninput = seek;
fields.forEach(id => $(id).addEventListener('input', preview));
function setFrame(hd) {
  $('screen').classList.toggle('hd', hd);
  for (const [id, selected] of [['hd',hd], ['reel',!hd]]) { $(id).classList.toggle('active',selected); $(id).setAttribute('aria-pressed',String(selected)); }
  $('frameSpec').textContent = hd ? '1920 × 1080 · 24 fps' : '1080 × 1920 · 24 fps';
  $('height').value = hd ? 12 : 24;
  preview();
}
$('reel').onclick = () => setFrame(false); $('hd').onclick = () => setFrame(true);
function place(event) { const frame = $('screen').getBoundingClientRect(); $('height').value = Math.round(Math.max(8, Math.min(70, (frame.bottom-event.clientY)/frame.height*100))); preview(); }
$('screen').onpointerdown = event => { $('screen').setPointerCapture(event.pointerId); place(event); };
$('screen').onpointermove = event => { if ($('screen').hasPointerCapture(event.pointerId)) place(event); };
$('screen').onpointerup = event => { if ($('screen').hasPointerCapture(event.pointerId)) $('screen').releasePointerCapture(event.pointerId); };
document.querySelectorAll('.swatch').forEach(button => button.onclick = () => {
  accent = button.dataset.color;
  document.querySelectorAll('.swatch').forEach(swatch => { swatch.classList.toggle('selected',swatch === button); swatch.setAttribute('aria-pressed',String(swatch === button)); });
  preview();
});
document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => {
  if (busy) return;
  mode = button.dataset.view;
  document.querySelectorAll('[data-view]').forEach(nav => nav.classList.toggle('active',nav.dataset.view === mode));
  document.querySelector('.sync-only').hidden = mode !== 'sync';
  $('pageTitle').textContent = mode === 'sync' ? 'Bring every word into time.' : 'Give your story a voice.';
  $('pageDescription').textContent = mode === 'sync' ? 'Fine-tune existing captions against the rhythm of your timeline.' : 'Turn timeline audio into captions that feel like part of the film.';
  submitLabel();
  status(mode === 'sync' ? 'Choose a sample SRT to explore the sync flow.' : 'Ready for your next story.');
});
function submitLabel() { $('submit').replaceChildren(document.createTextNode(mode === 'sync' ? 'Preview caption sync ' : 'Generate captions ')); const svg = document.createElementNS('http://www.w3.org/2000/svg','svg'); const use = document.createElementNS('http://www.w3.org/2000/svg','use'); use.setAttribute('href','#i-arrow'); svg.append(use); $('submit').append(svg); }
for (const [id,target,fallback] of [['reference','referenceName','Optional · TXT, DOCX or SRT'], ['srt','srtName','.srt subtitle file']]) $(id).onchange = () => { $(target).textContent = $(id).files[0]?.name || fallback; };
$('apiOpen').onclick = () => $('apiDialog').showModal();
$('showKey').onclick = () => { const show = $('apiKey').type === 'password'; $('apiKey').type = show ? 'text' : 'password'; $('showKey').textContent = show ? 'Hide' : 'Show'; };
$('demoConnect').onclick = () => { $('apiDialog').close(); $('accountLabel').textContent = 'ElevenLabs · Demo'; $('accountDot').style.background = '#92bd9b'; status('Demo account connected. No real API key is saved.'); };
function listPresets() { const selected = $('preset').value; $('preset').replaceChildren(new Option('Save your settings as a preset','')); Object.keys(presets).sort().forEach(name => $('preset').add(new Option(name,name))); if (Object.hasOwn(presets,selected)) $('preset').value = selected; }
$('savePreset').onclick = () => { $('presetDialog').showModal(); $('presetName').focus(); };
$('cancelPreset').onclick = () => $('presetDialog').close();
$('presetForm').onsubmit = event => {
  event.preventDefault(); const name = $('presetName').value.trim(); if (!name) return;
  presets[name] = Object.fromEntries(fields.map(id => [id, $(id).type === 'checkbox' ? $(id).checked : $(id).value]));
  presets[name].accent = accent;
  let message = `Preset saved: ${name}`;
  try { localStorage.setItem('srutilekha-studio-presets', JSON.stringify(presets)); } catch { message = `Preset saved for this session: ${name}`; }
  listPresets(); $('preset').value = name; $('presetDialog').close(); $('presetForm').reset(); status(message);
};
$('preset').onchange = () => {
  const preset = presets[$('preset').value]; if (!preset) return;
  fields.forEach(id => { if (preset[id] !== undefined) { if ($(id).type === 'checkbox') $(id).checked = Boolean(preset[id]); else $(id).value = preset[id]; } });
  accent = ['#ffe5a0','#ffffff','#b8e8c5'].includes(preset.accent) ? preset.accent : '#ffe5a0';
  document.querySelectorAll('.swatch').forEach(swatch => { const selected = swatch.dataset.color === accent; swatch.classList.toggle('selected', selected); swatch.setAttribute('aria-pressed', String(selected)); });
  preview(); status(`Preset applied: ${$('preset').value}`);
};
function showReview() {
  $('cueList').replaceChildren();
  captionSamples().forEach((text,index) => {
    const button = document.createElement('button'); button.className = 'cue';
    const timing = document.createElement('small'); timing.textContent = `00:${String(index*8).padStart(2,'0')} → 00:${String(index*8+6).padStart(2,'0')}`;
    const caption = document.createElement('span'); caption.textContent = text.replace('\n',' ');
    button.append(timing,caption); button.onclick = () => { stopPlaying(); $('scrub').value = index*8+.5; seek(); $('reviewDialog').close(); status(`Previewing sample caption ${index+1}.`); };
    $('cueList').append(button);
  });
  $('reviewDialog').showModal();
}
$('submit').onclick = () => {
  if (busy) return;
  if (Number($('minSecs').value) > Number($('maxSecs').value)) { status('Min duration must be less than or equal to max duration.'); $('minSecs').focus(); return; }
  stopPlaying(); busy = true; $('submit').disabled = true;
  const phases = ['Reading sample timeline…','Preparing demo captions…','Your preview is ready.'];
  let phase = 0; status(phases[0]); $('submit').textContent = 'Preparing preview…';
  const timer = setInterval(() => { phase++; status(phases[phase]); if (phase === 2) { clearInterval(timer); busy = false; $('submit').disabled = false; submitLabel(); if ($('review').checked) showReview(); else status('Preview complete. No captions were sent to Resolve.'); } }, 600);
};
$('mockImport').onclick = () => { $('reviewDialog').close(); status('Preview complete. The desktop app imports captions into Resolve.'); };
for (let index = 0; index < 90; index++) { const bar = document.createElement('b'); bar.style.height = (5 + Math.abs(Math.sin(index*.83)*Math.cos(index*.27))*24) + 'px'; $('waveBars').append(bar); }
listPresets(); seek();
