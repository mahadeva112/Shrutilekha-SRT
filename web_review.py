"""Caption review for the WebView2 studio: Tk-free ports of App's review logic.

Each function mirrors the App method named in its docstring, so a cut,
split, merge or Apply from the web page produces the same cues and the same
SRT/.cap files as the Tk review editor. Segments travel to and from the page
as {"s", "e", "spk", "words": [[start, end, text], ...], "text"}.
"""
import os

# (label, value key, lo, hi, step, format) — App._split_field_specs.
SPLIT_FIELDS = (
    ("Max characters", "max_chars", 8, 60, 1, "%d"),
    ("Lines per cue", "max_lines", 1, 4, 1, "%d"),
    ("Max seconds", "max_secs", 0.5, 8, 0.1, "%.1f"),
    ("CPS limit", "cps", 0, 40, 1, "%d"),
    ("Min duration", "min_secs", 0, 3, 0.1, "%.1f"),
    ("Max words", "words_per", 0, 12, 1, "%d"),
)
# App.SPLIT_RECIPES: (max chars, lines, max secs, cps, min duration, max words)
RECIPES = (
    ("Fast", (21, 2, 3.0, 30, 0.5, 0)),
    ("Standard", (15, 1, 2.0, 25, 0.4, 0)),
    ("Readable", (12, 2, 2.5, 17, 0.8, 0)),
)
SETTINGS_DEFAULTS = ("15", "1", "2")
WAVE_POINTS = 2400


def fmt_ts(sec):
    """App._fmt_ts."""
    sec = max(0.0, sec)
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def wrapped_texts(srt_path, segs):
    """Give each segment the line-wrapped text transcribe.py wrote to the SRT.

    The .cap sidecar stores one word per WRD line, so the text rebuilt from it
    is a single line. Using that in the review dropped the wrap, and a
    "Lines per cue: 2" run came out of Apply as one long line. The SRT holds
    the wrapped text; it is used for every cue whose words match, cue for cue.
    """
    if not srt_path or not segs:
        return segs
    try:
        import transcribe as T
        cues = T.parse_srt(srt_path)
    except Exception:
        return segs
    if len(cues) != len(segs):
        return segs
    for seg, (_s, _e, text) in zip(segs, cues):
        if text.split() == seg["text"].split():
            seg["text"] = text
    return segs


def parse_cap(cap_path, srt_path=None):
    """App._parse_cap: (header lines, segments) from the .cap sidecar."""
    header, segs, cur = [], [], None
    try:
        with open(cap_path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("FPS ") or line.startswith("SPK "):
                    header.append(line)
                elif line.startswith("SEG "):
                    parts = line.split(None, 3)
                    cur = {"s": float(parts[1]), "e": float(parts[2]),
                           "spk": int(parts[3]) if len(parts) > 3 else 0, "words": []}
                    segs.append(cur)
                elif line.startswith("WRD ") and cur is not None:
                    parts = line.split(None, 3)
                    cur["words"].append((float(parts[1]), float(parts[2]),
                                         parts[3] if len(parts) > 3 else ""))
    except Exception:
        return [], []
    for seg in segs:
        seg["text"] = " ".join(w[2] for w in seg["words"])
    return header, wrapped_texts(srt_path, segs)


def spk_colors(header):
    """App._parse_spk_colors."""
    colors = {}
    for line in header:
        if line.startswith("SPK "):
            parts = line.split(None, 3)
            if len(parts) >= 3:
                try:
                    colors[int(parts[1])] = parts[2]
                except ValueError:
                    pass
    return colors


def write_srt_cap(srt_path, cap_path, header, segs):
    """App._write_srt_cap."""
    srt = ["1\n00:00:00,000 --> 00:00:00,001\n \n"]
    for i, seg in enumerate(segs, start=1):
        srt.append("%d\n%s --> %s\n%s\n" % (i + 1, fmt_ts(seg["s"]), fmt_ts(seg["e"]), seg["text"]))
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt))
    cap = list(header)
    for seg in segs:
        cap.append("SEG %.3f %.3f %d" % (seg["s"], seg["e"], seg["spk"]))
        orig = " ".join(w[2] for w in seg["words"])
        new_words = seg["text"].split()
        # Compared word by word: a line break in the text is a wrap, not an
        # edit, and must not throw away the real word timings.
        if new_words == orig.split() and seg["words"]:
            for ws, we, txt in seg["words"]:
                cap.append("WRD %.3f %.3f %s" % (ws, we, txt))
        elif new_words:
            n = len(new_words)
            step = max(0.001, seg["e"] - seg["s"]) / n
            for j, wtok in enumerate(new_words):
                cap.append("WRD %.3f %.3f %s" % (seg["s"] + j * step, seg["s"] + (j + 1) * step, wtok))
    with open(cap_path, "w", encoding="utf-8") as f:
        f.write("\n".join(cap) + "\n")


def normalize(seg):
    """A segment from the page, with word triples as tuples."""
    return {"s": float(seg["s"]), "e": float(seg["e"]), "spk": int(seg.get("spk") or 0),
            "words": [(float(w[0]), float(w[1]), str(w[2])) for w in seg.get("words", [])],
            "text": str(seg.get("text") or "")}


def live_segment(seg):
    """App._live_segment: fold edited text back in, keeping word timing."""
    seg = dict(normalize(seg))
    seg["text"] = seg["text"].strip()
    tokens = seg["text"].split()
    words = seg["words"]
    if len(tokens) == len(words):
        seg["words"] = [(start, end, text) for (start, end, _), text in zip(words, tokens)]
    elif tokens:
        step = max(.001, seg["e"] - seg["s"]) / len(tokens)
        seg["words"] = [(seg["s"] + i * step, seg["s"] + (i + 1) * step, text)
                        for i, text in enumerate(tokens)]
    else:
        seg["words"] = []
    return seg


def settings(values, language_codes):
    """App._split_settings, from plain form values."""
    def num(key, default, cast):
        try:
            return cast(float(values.get(key)))
        except (TypeError, ValueError):
            return default
    d0, d1, d2 = SETTINGS_DEFAULTS
    return {
        "max_chars": max(1, num("max_chars", int(d0), int)),
        "max_lines": max(1, num("max_lines", int(d1), int)),
        "max_secs": max(0.1, num("max_secs", float(d2), float)),
        "cps": max(0.0, num("cps", 25.0, float)),
        "min_dur": max(0.0, num("min_secs", 0.4, float)),
        "max_words": max(0, num("words_per", 0, int)),
        "lang": language_codes.get(values.get("lang"), "auto"),
    }


def resplit(live_segs, s):
    """App._resplit_segments: regroup every word under new split settings."""
    import transcribe as T
    words = []
    for seg in live_segs:
        spk = seg.get("spk", 0)
        for ws, we, txt in seg["words"]:
            words.append(T._Word(txt, ws, we, spk if spk else None))
    cues = T.build_cues(words, s["max_chars"], s["max_lines"], s["max_secs"],
                        include_punct="1", cps=s["cps"], max_words=s["max_words"], lang=s["lang"])
    cues = T._sanitize_cues(cues, read_dur=s["min_dur"])
    segs = []
    for _idx, cs, ce, text, cue_words in cues:
        spk = next((w[3] for w in cue_words if len(w) > 3 and w[3]), 0)
        segs.append({"s": cs, "e": ce, "spk": spk,
                     "words": [(w[1], w[2], w[0]) for w in cue_words], "text": text})
    return segs


def split(segs, i, n_left, s):
    """The row's _split_here: one new boundary, outer edges unchanged."""
    import transcribe as T
    current = segs[i]
    words = current.get("words", [])
    if len(words) < 2:
        return None
    n_left = max(1, min(int(n_left), len(words) - 1))
    left_words, right_words = words[:n_left], words[n_left:]
    left_text = T.wrap(" ".join(w[2] for w in left_words), s["max_chars"], s["max_lines"], s.get("lang"))
    right_text = T.wrap(" ".join(w[2] for w in right_words), s["max_chars"], s["max_lines"], s.get("lang"))
    cut = right_words[0][0]
    left_end = left_words[-1][1]
    if 0.0 < cut - left_end <= T._GAP_CLOSE_MAX:
        left_end = cut - 0.001
    left_end = max(current["s"] + 0.001, min(left_end, cut - 0.001))
    out = list(segs)
    out[i:i + 1] = [
        {"s": current["s"], "e": left_end, "spk": current.get("spk"), "words": left_words, "text": left_text},
        {"s": cut, "e": max(current["e"], cut + 0.001), "spk": current.get("spk"),
         "words": right_words, "text": right_text},
    ]
    return out


def merge(segs, i, s):
    """The row's _merge_next: cue i absorbs cue i + 1."""
    import transcribe as T
    if i + 1 >= len(segs):
        return None
    current, following = segs[i], segs[i + 1]
    combined = (current["text"].strip() + " " + following["text"].strip()).strip()
    out = list(segs)
    out[i] = {"s": current["s"], "e": following["e"], "spk": current.get("spk"),
              "words": current.get("words", []) + following.get("words", []),
              "text": T.wrap(" ".join(combined.split()), s["max_chars"], s["max_lines"], s.get("lang"))}
    del out[i + 1]
    return out


def audio_path(args_path):
    """App._audio_path: first line of the args file."""
    try:
        with open(args_path, encoding="utf-8") as f:
            return f.readline().rstrip("\r\n") or None
    except Exception:
        return None


def envelope(path, points=WAVE_POINTS):
    """The peak envelope transcribe.py computes, thinned for drawing."""
    if not path or not os.path.exists(path):
        return None
    try:
        import transcribe as T
        env, hop = T._audio_envelope(path), T._ENV_HOP
    except Exception:
        return None
    if not env:
        return None
    step = max(1, -(-len(env) // points))
    peaks = [round(max(env[i:i + step]), 3) for i in range(0, len(env), step)]
    return {"env": peaks, "hop": hop * step, "dur": len(env) * hop}
