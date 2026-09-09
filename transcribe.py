"""Called by audio_to_srt.py: transcribes audio and writes an SRT file.

Usage: python3 transcribe.py <audio_path> <srt_output_path> <max_chars> <max_lines> <max_secs>
"""

import array
import difflib
import html
import math
import os
import re
import ssl
import subprocess
import sys
import unicodedata

# Per-language segmentation tables: one module per language, plus the
# writing-system data they share. Data only — every rule that acts on it
# lives in this file, so all 13 languages run the same splitter.
import languages
from languages import scripts as _scripts

# Everything this script prints is read back by loader.pyw, which decodes the
# pipe as UTF-8. A piped child's stdout, though, defaults to the machine's
# locale codepage (cp1252 on a Western Windows install) — so a source filename
# written in Devanagari killed the run outright with UnicodeEncodeError on the
# "Transcribing: <name>" line, and anything merely non-ASCII arrived as mojibake
# in the log and in the error dialog. Pin both streams to UTF-8 to match the
# reader, with errors="replace" so no message can ever be fatal.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Networks that inspect TLS (corporate proxies, some antivirus suites) re-sign
# every HTTPS response with a private root CA. Windows trusts that root, so the
# browser is happy — but Python isn't, because the ElevenLabs SDK verifies
# against certifi's bundle rather than the OS store, and certifi has never heard
# of the company root. truststore points verification at the Windows store, so
# the SDK trusts exactly what the rest of the machine already trusts.
#
# Missing package or a non-Windows box: fall through silently. certifi still
# works fine on any network that isn't intercepting, and if it isn't fine
# _explain() below turns the resulting failure into a readable message.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass


def _progress(pct, msg):
    """Emit a progress marker the loader.pyw GUI parses. Stays harmless when
    transcribe.py is run standalone (just prints a line)."""
    try:
        print("PROGRESS|%d|%s" % (int(pct), msg), flush=True)
    except Exception:
        pass


_progress(5, "Initializing...")

# Always resolve relative to this script's own folder — works on any machine
PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))

# Language forced on the ElevenLabs Scribe API so every transcript is Hindi in
# Devanagari script — code-switched English words included. Overridable via the
# ELEVENLABS_LANGUAGE env var (ISO 639-1 "hi" or 639-3 "hin"); resolved at call
# time so a value set in .env (loaded in main) is honored.
HINDI_LANG_CODE = "hin"


# "auto" means don't pin a language: Scribe detects whatever is spoken and may
# return any language/script. Sent by the loader as lang_code="auto"; fetch_words
# then omits language_code entirely.
def is_auto_lang(code):
    return (code or "").strip().lower() in ("auto", "any", "detect")

# One machine has the elevenlabs package unpacked at C:\el to work around the
# Windows MAX_PATH limit. setup.bat installs it normally (pip --user), so this
# is only a fallback for that install — added only when the folder is actually
# there, rather than pushing a non-existent path onto every machine's sys.path.
_EL_FALLBACK = r"C:\el"
if os.path.isdir(_EL_FALLBACK) and _EL_FALLBACK not in sys.path:
    sys.path.insert(0, _EL_FALLBACK)

def load_dotenv():
    env_file = os.path.join(PIPELINE_DIR, ".env")
    if not os.path.exists(env_file):
        return
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def fmt_ts(seconds):
    ms = int(round(seconds * 1000))
    h, r = divmod(ms, 3600000)
    m, r = divmod(r, 60000)
    s, ms = divmod(r, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


# ── Visual length ───────────────────────────────────────────────────────────
# max_chars is a LINE WIDTH, so every budget derived from it — the character cap
# in build_cues, the reading-speed cap, the wrapper's own per-line budget — is
# asking how much text fits on screen, not how many Unicode codepoints the text
# happens to be encoded in.
#
# For Latin the two are identical, which is why plain len() went unnoticed. For
# the Indic scripts they are not, and not by a little: measured against the
# akshara (the consonant-plus-marks cluster that is one visual unit and one font
# cluster), a Kannada word averages 1.71 codepoints per akshara, Telugu 1.86,
# Tamil 1.73, Malayalam 1.61, Devanagari 1.58. Counting codepoints therefore
# shrinks the real line budget by that factor, and Kannada — the longest words
# of the set on top of the inflation — fitted barely half of what Hindi did at
# the same setting. Cues were force-closed before any phrase could finish, so
# every one came out a fragment however well the boundary scoring worked: there
# was no longer a choice of boundary left to score.
#
# _vlen counts aksharas, so one max_chars means the same width in every script:
#   • combining marks (Mn/Mc — vowel signs, anusvara, nukta, virama) belong to
#     the akshara they sit on and are not counted on their own. Mc marks do take
#     their own advance width, so a matra-heavy word is very slightly
#     under-counted; the akshara is still the unit a reader scans.
#   • format characters (Cf — ZWJ/ZWNJ and the bidi marks Urdu arrives with) are
#     invisible and never counted.
#   • a virama LINKS: in ಇರುತ್ತದೆ the ತ್+ತ is one conjunct glyph, so a consonant
#     following a virama joins the cluster before it instead of opening a new
#     one. How much width that conjunct then costs depends on how the script
#     builds it, which is the difference between the two tables below.
#
# Kannada and Telugu stack a conjunct VERTICALLY — the second consonant is a
# subscript under the first, so ತ್ತ is one akshara wide and costs 1.
# Which viramas link, and what the conjunct then costs: see
# languages/scripts.py, which is also where Tamil's non-ligating pulli is
# explained.
_STACKING_VIRAMA = _scripts.STACKING_VIRAMA
_JOINING_VIRAMA = _scripts.JOINING_VIRAMA
_MARK_CATS = frozenset(("Mn", "Mc", "Cf"))


def _vlen(text):
    """Visual length of ``text``, in aksharas / grapheme clusters."""
    n = 0
    link = 0          # pending virama: 0 none, 1 horizontal join, 2 vertical stack
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in _MARK_CATS:
            cp = ord(ch)
            if cp in _JOINING_VIRAMA:
                link = 1
            elif cp in _STACKING_VIRAMA:
                link = 2
            continue
        if link and cat[0] == "L":
            # Consonant pulled into the cluster by the virama before it. A
            # horizontal conjunct costs one extra unit for the width it adds; a
            # stacked one costs nothing, being no wider than a bare akshara.
            if link == 1:
                n += 1
            link = 0
            continue
        # A virama with no consonant after it is a bare vowel-killer (Malayalam
        # "ഇത്", Devanagari "सम्"), not a conjunct — it adds no width.
        link = 0
        n += 1
    return n


def wrap(text, max_chars, max_lines, lang=None):
    """Greedy word-wrap into at most ``max_lines`` lines of ``max_chars``.

    Never drops words: once the line budget is exhausted, remaining words
    overflow onto the final line. A slightly long line is always better than
    silently losing text (the old version broke out of the loop and dropped
    every word past the last line).

    When ``lang`` is set (or the text is in a recognised Indic script), the
    wrapper also respects grammatical cohesion:
      • A bind-back word (auxiliary, copula, postposition — "है", "सकता",
        "ছিল", "ہے", etc.) never opens a new line; it stays with the word
        it completes, even if the line overflows a little.
      • A bind-forward word (conjunction, subordinator — "और", "लेकिन",
        "কিন্তু", "اور", etc.) never closes a line; it moves to the next
        line so it stays with the clause it introduces."""
    words = text.split()
    if not words:
        return ""
    lines = []
    current = ""
    for i, word in enumerate(words):
        candidate = (current + " " + word).strip() if current else word
        if not current or _vlen(candidate) <= max_chars:
            current = candidate
        elif _binds_back(word, lang):
            # This word completes the previous phrase — keep it on the
            # same line even if it overflows, rather than orphaning it.
            current = candidate
        elif len(lines) + 1 < max_lines:
            # About to break here.  Check whether the last word of the
            # current line is a bind-forward word.  If so, move it to the
            # new line so it stays with the clause it introduces.
            cur_words = current.split()
            if cur_words and _binds_fwd(cur_words[-1], lang):
                carry = cur_words.pop()       # pull the conjunction off
                current = " ".join(cur_words) if cur_words else ""
                word = carry + " " + word     # prepend it to the new line
            if current:
                lines.append(current)
            current = word
        else:
            current = candidate        # budget spent → overflow, never drop
    if current:
        lines.append(current)
    return "\n".join(lines)


# ── Script detection ────────────────────────────────────────────────────────
# Two different questions are asked about a token's script, and they need
# different answers:
#
#   1. "Which FONT does this cue need?" — a Resolve subtitle item can carry only
#      ONE font, and only Devanagari and Bengali are mapped, so _char_script /
#      _word_script deliberately answer 'dev', 'beng' or None. A Tamil token is
#      None here: there is no Tamil font rule to apply, and claiming a script
#      would start splitting cues the importer cannot style differently anyway.
#   2. "Which language's grammar rules apply?" — cue splitting needs the real
#      script so it can consult the right function-word table (Tamil clitics for
#      a Tamil token, Gurmukhi ones for Punjabi …). That is _token_script, and
#      it covers every script the supported Indian languages are written in.
#
# IMPORTANT: several codepoints sit inside a script's block but are shared —
# danda ।(U+0964) / double danda ॥(U+0965) are used by nearly every Indic
# script, the Vedic tone marks U+0951–U+0952 likewise, and the Arabic block
# holds the punctuation Urdu shares with Arabic (، ؛ ؟ ۔). None of them may
# decide a token's script.
_SCRIPT_RANGES = _scripts.SCRIPT_RANGES

# Script-neutral codepoints that live inside a script block (see above).
_NEUTRAL_CPS = _scripts.NEUTRAL_CPS


def _script_of_cp(cp):
    """Full script id of a codepoint: 'dev', 'beng', 'taml', 'arab', … or None
    for Latin, digits, punctuation and the pan-Indic marks above."""
    if cp in _NEUTRAL_CPS:
        return None
    for name, ranges in _SCRIPT_RANGES:
        for lo, hi in ranges:
            if lo <= cp <= hi:
                return name
    return None


def _char_script(cp):
    """Script of a codepoint for FONT purposes: 'dev', 'beng' or None."""
    s = _script_of_cp(cp)
    return s if s in ("dev", "beng") else None


def _token_script(token):
    """Script a token is written in, across every supported Indic script plus
    Perso-Arabic. Used to pick the grammar table, never to pick a font."""
    for ch in token:
        s = _script_of_cp(ord(ch))
        if s:
            return s
    return None


def _word_script(token):
    """Script of a token: 'dev' if it contains ANY Devanagari char (so no
    Hindi word is ever missed), else 'beng' if it contains Bengali, else
    None (digits, Latin, punctuation — script-neutral)."""
    found_beng = False
    for ch in token:
        s = _char_script(ord(ch))
        if s == "dev":
            return "dev"
        if s == "beng":
            found_beng = True
    return "beng" if found_beng else None


def _buf_script(buf):
    """Dominant script of the words currently buffered in a cue."""
    for entry in buf:
        s = _word_script(entry[0])
        if s:
            return s
    return None


# Sentence-end punctuation across the supported scripts. A word ending in one
# of these is a "strong" boundary — never carry past it into the same cue when
# avoidable. Indic scripts share the danda ।/॥ (Devanagari, Bengali, Gurmukhi,
# Gujarati, Odia; the southern four normally use the Latin full stop), while
# Urdu has its own full stop ۔ and question mark ؟ — omitting those made every
# Urdu cue boundary look unpunctuated to the splitter.
_STRONG_END = _scripts.STRONG_END
_WEAK_END = _scripts.WEAK_END
_END_TRIM = _scripts.END_TRIM

# Punctuation removed from the DISPLAY text when include_punct is off. Built
# from the two tables above rather than written out again: a hand-written list
# drifted from them and left the fullwidth marks (？！，、) and the dashes (—–)
# on screen in a mode whose whole point is that they are not there.
_PUNCT_OFF_RE = re.compile(
    "[" + re.escape("".join(sorted(set(_STRONG_END + _WEAK_END)))) + "]")


def _ends_with(token, suffixes):
    t = token.rstrip(_END_TRIM)
    return any(t.endswith(s) for s in suffixes)


# ── Latin → target-script safety net ────────────────────────────────────────
# With language_code pinned ElevenLabs usually writes spoken English in the
# target script (fast food → फास्ट-फूड), but the API regularly still emits a
# Latin token ("number", "ok"). Left alone that token stays Latin in the cue —
# visually jarring, and script-neutral to _word_script, so it also can't be
# given the right font. Any Latin run is therefore transliterated into the
# target script here, in two layers:
#
#   1. data/translit_<script>.json.gz — 117k words derived from the CMU
#      Pronouncing Dictionary, so the spelling follows how the word is *said*
#      rather than how it is spelt. That distinction is the whole ballgame:
#      letter-by-letter, "neurological" comes out नेउरोलोगिकाल; from its
#      pronunciation it comes out न्यूरोलॉजिकल. Some 220 words where English
#      is too irregular for any rule are hand-corrected on top. Generated by
#      tools/build_translit.py — edit tools/translit_exceptions.py and rerun,
#      do not patch the .json.gz.
#   2. the letter-based phonetic rules below, for anything not in that
#      dictionary: invented words, names, transcription fragments. Rough, but
#      it guarantees the token ends up in the target script, which is what
#      _word_script and the Resolve-side font mapper need.
#
# Neither layer needs a network call, an API key or a third-party package at
# transcription time; the dictionary is a data file that ships with the tool.
#
# 'dev' (Hindi/Marathi/Nepali/Sanskrit) and 'beng' (Bengali/Assamese) each have
# both layers of their own. Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada and
# Malayalam get both for free instead: the Indic blocks are laid out in
# parallel, so a word resolved in Devanagari converts to any of them by adding a
# fixed offset to every codepoint (_fold_from_dev, with the handful of
# corrections in languages/scripts.py). That is why those seven need no
# dictionary and no consonant table — they inherit the Devanagari ones.
#
# Urdu is the exception and is NOT supported: Perso-Arabic shares no layout with
# the Indic blocks, so it cannot be reached this way and needs a _TRANSLIT row
# and a dictionary of its own. Latin words in an Urdu transcript stay Latin.


# Rule-based fallback: approximate phonetic mapping, guarantees Devanagari.
_DEV_DIGRAPH_C = {
    "sh": "श", "ch": "च", "ck": "क", "ph": "फ", "th": "थ", "wh": "व",
    "gh": "घ", "kh": "ख", "bh": "भ", "dh": "ध", "qu": "क्व",
}
_DEV_C = {
    "b": "ब", "c": "क", "d": "ड", "f": "फ", "g": "ग", "h": "ह", "j": "ज",
    "k": "क", "l": "ल", "m": "म", "n": "न", "p": "प", "q": "क", "r": "र",
    "s": "स", "t": "ट", "v": "व", "w": "व", "x": "क्स", "y": "य", "z": "ज़",
}
_DEV_DIGRAPH_V = {  # (matra-after-consonant, independent) forms
    "ee": ("ी", "ई"), "oo": ("ू", "ऊ"), "ea": ("ी", "ई"), "ai": ("ै", "ऐ"),
    "ay": ("े", "ए"), "au": ("ौ", "औ"), "oa": ("ो", "ओ"), "ey": ("े", "ए"),
    "ie": ("ी", "ई"), "ue": ("ू", "ऊ"), "ew": ("ू", "ऊ"), "ou": ("ाउ", "आउ"),
}
_DEV_V = {
    "a": ("ा", "अ"), "e": ("े", "ए"), "i": ("ि", "इ"),
    "o": ("ो", "ओ"), "u": ("ु", "उ"),
}
_VOWELS = "aeiou"
_DOUBLE_CONS = re.compile(r"([bcdfgklmnprstvz])\1")

# Bengali tables — same structure, same phonetic engine, different glyphs.
_BEN_DIGRAPH_C = {
    "sh": "শ", "ch": "চ", "ck": "ক", "ph": "ফ", "th": "থ", "wh": "ও",
    "gh": "ঘ", "kh": "খ", "bh": "ভ", "dh": "ধ", "qu": "কু",
}
_BEN_C = {
    "b": "ব", "c": "ক", "d": "ড", "f": "ফ", "g": "গ", "h": "হ", "j": "জ",
    "k": "ক", "l": "ল", "m": "ম", "n": "ন", "p": "প", "q": "ক", "r": "র",
    "s": "স", "t": "ট", "v": "ভ", "w": "ও", "x": "ক্স", "y": "য়", "z": "জ",
}
_BEN_DIGRAPH_V = {
    "ee": ("ী", "ঈ"), "oo": ("ূ", "ঊ"), "ea": ("ী", "ঈ"), "ai": ("ৈ", "ঐ"),
    "ay": ("ে", "এ"), "au": ("ৌ", "ঔ"), "oa": ("ো", "ও"), "ey": ("ে", "এ"),
    "ie": ("ী", "ঈ"), "ue": ("ূ", "ঊ"), "ew": ("ূ", "ঊ"), "ou": ("াউ", "আউ"),
}
_BEN_V = {
    "a": ("া", "আ"), "e": ("ে", "এ"), "i": ("ি", "ই"),
    "o": ("ো", "ও"), "u": ("ু", "উ"),
}

# script → (consonant digraphs, consonants, vowel digraphs, vowels, virama,
#           standalone 'r'). Add a script by adding a row.
_TRANSLIT = {
    "dev":  (_DEV_DIGRAPH_C, _DEV_C, _DEV_DIGRAPH_V, _DEV_V, "्", "र"),
    "beng": (_BEN_DIGRAPH_C, _BEN_C, _BEN_DIGRAPH_V, _BEN_V, "্", "র"),
}


# Pronunciation-derived dictionaries, read on first use and kept for the run.
# Loading is lazy because most transcripts are already fully in the target
# script: a Hindi-pinned run typically leaks a couple of dozen Latin words, and
# plenty leak none at all, in which case the file is never touched.
_DICTIONARIES = {}


def _translit_dictionary(script):
    """{english: indic} for ``script``. Missing or unreadable data leaves the
    rule-based fallback to cope on its own rather than failing the run — the
    spellings get rougher, but every Latin token still reaches the target
    script, which is the property the rest of the pipeline depends on."""
    if script in _DICTIONARIES:
        return _DICTIONARIES[script]
    table = {}
    path = os.path.join(PIPELINE_DIR, "data", "translit_%s.json.gz" % script)
    try:
        import gzip
        import json
        with gzip.open(path, "rb") as f:
            table = json.loads(f.read().decode("utf-8"))
    except Exception as e:
        print("Transliteration dictionary unavailable (%s: %s); "
              "falling back to phonetic rules." % (os.path.basename(path), e))
    _DICTIONARIES[script] = table
    return table


def _rule_translit(word, script="dev"):
    """Phonetic Latin→Indic for a lowercase a-z word. Approximate by nature
    (English spelling is irregular) but always fully in the target script —
    fast→फास्ट/ফাস্ট, food→फूड/ফুড, market→मार्केट/মার্কেট."""
    dig_c, cons, dig_v, vowels, virama, r_char = _TRANSLIT[script]
    # A doubled English consonant is one sound, not a cluster: without this
    # "password" comes out पास्स्वोर्ड instead of पासवोर्ड.
    word = _DOUBLE_CONS.sub(r"\1", word)
    out = []
    prev_cons = False
    i, n = 0, len(word)
    while i < n:
        two = word[i:i + 2]
        # 'er' with no vowel after = schwa+r (super→सुपर, market→मार्केट)
        if two == "er" and prev_cons and (i + 2 >= n or word[i + 2] not in _VOWELS):
            out.append(r_char)
            prev_cons = True
            i += 2
            continue
        if two in dig_v:
            m, ind = dig_v[two]
            out.append(m if prev_cons else ind)
            prev_cons = False
            i += 2
            continue
        if two in dig_c:
            if prev_cons:
                out.append(virama)        # virama joins the cluster
            out.append(dig_c[two])
            prev_cons = True
            i += 2
            continue
        # Soft 'c' before e/i/y is /s/, not /k/ (city→सिटी, cell→सेल)
        if (word[i] == "c" and i + 1 < n and word[i + 1] in "eiy"
                and word[i:i + 2] not in dig_c):
            if prev_cons:
                out.append(virama)
            out.append(cons["s"])
            prev_cons = True
            i += 1
            continue
        # Final '-y' after a consonant is a vowel, not य (happy→हैपी, city→सिटी)
        if word[i] == "y" and i == n - 1 and prev_cons:
            out.append(dig_v["ee"][0])
            prev_cons = False
            i += 1
            continue
        # Final '-le' is a syllable of its own — no virama, so the preceding
        # consonant keeps its inherent vowel (little→लिटल, not लिट्ल)
        if word[i:] == "le" and prev_cons:
            out.append(cons["l"])
            prev_cons = True
            break
        ch = word[i]
        if ch in vowels:
            m, ind = vowels[ch]
            # silent final 'e' (love, table) — drop it
            if ch == "e" and i == n - 1 and prev_cons and n > 2:
                i += 1
                continue
            out.append(m if prev_cons else ind)
            prev_cons = False
        elif ch in cons:
            if prev_cons:
                out.append(virama)        # consonant cluster
            out.append(cons[ch])
            prev_cons = True
        else:
            out.append(ch)                      # digits/symbols pass through
            prev_cons = False
        i += 1
    return "".join(out)


_LATIN_RUN = re.compile(r"[A-Za-z]+")


# Punctuation stripped when a word is normalized for comparison — covers the
# Devanagari danda/double danda and curly quotes as well as ASCII marks.
_PUNCT_STRIP = "।॥.?!,;:—–-\"“”‘’'()[]{}"


_DEFAULT_SPEAKER_COLORS = [
    "#FFFFFF", "#FFD400", "#00E5FF", "#7CFC00",
    "#FF6EC7", "#FFA500", "#B388FF", "#FF5252",
]


def load_speaker_colors():
    """Palette assigned to diarization speakers in order of appearance. Read
    from speaker_colors.json (a JSON array of hex strings) if present, else a
    sensible high-contrast default."""
    path = os.path.join(PIPELINE_DIR, "speaker_colors.json")
    if os.path.exists(path):
        try:
            import json
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            colors = [c for c in data if isinstance(c, str) and c.strip()]
            if colors:
                return colors
        except Exception:
            pass
    return list(_DEFAULT_SPEAKER_COLORS)


# Where each script's block starts. Read off SCRIPT_RANGES — the first range of
# an entry IS the block base — rather than written out again, so adding a script
# there is enough and the two can never disagree.
_BLOCK_BASE = {name: ranges[0][0] for name, ranges in _SCRIPT_RANGES}
_TRANSLIT_VIA_DEV = _scripts.TRANSLIT_VIA_DEV
_TRANSLIT_FOLD = _scripts.TRANSLIT_FOLD

# Offsets within every Indic block, so they are the same number in each: the
# consonant range क..ह, the virama, and the anusvara.
_OFF_CONS_LO, _OFF_CONS_HI = 0x15, 0x39
_OFF_VIRAMA, _OFF_ANUSVARA = 0x4D, 0x02


def _is_cons(cp, base):
    return base + _OFF_CONS_LO <= cp <= base + _OFF_CONS_HI


def _polish(text, script, base):
    """Orthographic corrections the codepoint shift cannot make.

    The shift gets a spelling into the target block; these get it into the
    target's actual writing conventions. Applied only to the transliterator's
    own output, never to text the API sent.
    """
    if script == "guru":
        # Punjabi writes clusters without a visible halant (ਸਕੂਲ, ਡਾਕਟਰ); it
        # survives only before the subjoined consonants.
        out = []
        for i, ch in enumerate(text):
            if ord(ch) == base + _OFF_VIRAMA:
                nxt = text[i + 1] if i + 1 < len(text) else ""
                if nxt not in _scripts.GURU_SUBJOINED:
                    continue
            out.append(ch)
        # Nasal: tippi after a short vowel, bindi after a long or independent
        # one. The shift always produces bindi.
        text = "".join(out)
        out = []
        for i, ch in enumerate(text):
            if (ord(ch) == base + _OFF_ANUSVARA
                    and (i == 0 or text[i - 1] not in _scripts.GURU_BINDI_AFTER)):
                out.append("ੰ")
                continue
            out.append(ch)
        return "".join(out)

    if script == "taml":
        out = []
        for i, ch in enumerate(text):
            if ord(ch) == base + _OFF_ANUSVARA:
                nxt = text[i + 1] if i + 1 < len(text) else ""
                repl = _scripts.TAML_NASAL_DEFAULT
                for group, nasal in _scripts.TAML_NASAL:
                    if nxt in group:
                        repl = nasal
                        break
                out.append(repl)
                continue
            out.append(ch)
        text = "".join(out)

    if script not in _scripts.TRANSLIT_DROPS_FINAL_SCHWA and text:
        # Put back the vowel-killer Devanagari does not need. Without it the
        # inherent vowel sounds: ब्रेड would read /brēḍa/, not /brēḍ/.
        last = text[-1]
        if _is_cons(ord(last), base):
            chillu = (_scripts.MLYM_CHILLU.get(last)
                      if script == "mlym" else None)
            text = text[:-1] + chillu if chillu else text + chr(base + _OFF_VIRAMA)
    return text


def _fold_from_dev(text, script):
    """Devanagari ``text`` rewritten in ``script``: fold, shift, polish.

    The Indic blocks share a layout, so the same offset within each block is the
    same letter and the script change is arithmetic. Two things bracket it:
    characters the target block has nothing at are folded into ones it does have
    first, and the conventions the arithmetic cannot know about — Tamil's
    missing voiced series, the final virama the Dravidian scripts need,
    Gurmukhi's unwritten halant — are applied after. Both tables live in
    languages/scripts.py. Anything outside the Devanagari block — digits,
    spaces, punctuation the dictionary carries — passes through untouched.
    """
    base = _BLOCK_BASE[script]
    fold = _TRANSLIT_FOLD.get(script) or {}
    out = []
    for ch in text:
        for c in fold.get(ch, ch):   # a fold may map to "" or to another letter
            cp = ord(c)
            out.append(chr(cp - 0x0900 + base)
                       if 0x0900 <= cp <= 0x097F else c)
    return _polish("".join(out), script, base)


def _clamp_stray_dev(text, script):
    """Rewrite a Devanagari codepoint that has no business being in ``script``.

    A spelling that comes out of a non-Devanagari dictionary should contain no
    Devanagari, and 1,341 entries of data/translit_beng.json.gz do: the CMU rule
    for /ɪər/ and /ɛər/ leaks the Devanagari i- and e-matra, so `adhere` is
    stored as অড্হिয়ার with U+093F where U+09BF belongs.

    Left alone that single character makes _word_script call the whole word
    Devanagari, which flushes the cue around it (see the script-boundary rule
    in build_cues) while the Resolve-side script still picks a Bengali font by
    majority — so the matra renders as tofu inside a cue that was split for no
    reason. The blocks are parallel, so the right character is the same offset
    in the right block.

    tools/build_translit.py is not in this checkout, so the .json.gz cannot be
    regenerated; clamping at read time is the available fix, and it is harmless
    once the data is corrected.
    """
    base = _BLOCK_BASE.get(script)
    if base is None or base == 0x0900:
        return text
    return "".join(chr(ord(c) - 0x0900 + base)
                   if 0x0900 <= ord(c) <= 0x097F else c for c in text)


# Every script a Latin word can be written into: the two with dictionaries and
# rule tables of their own, plus the ones reached from Devanagari by offset.
# script_for_lang() and _dominant_script() both read this, so coverage is
# decided in exactly one place.
_TRANSLIT_SCRIPTS = frozenset(_TRANSLIT) | _TRANSLIT_VIA_DEV


def transliterate(text, script):
    """Replace every Latin-letter run in ``text`` with ``script``.

    Dictionary lookup first, phonetic rules otherwise. Scripts without tables of
    their own are resolved in Devanagari and then folded across
    (_fold_from_dev), which gives them the 117k pronunciation-derived dictionary
    and the rule fallback in one step rather than needing their own copy of
    either. Non-Latin content is untouched; an unknown/None script returns the
    text unchanged.
    """
    if script not in _TRANSLIT_SCRIPTS:
        return text
    via_dev = script not in _TRANSLIT
    lookup = "dev" if via_dev else script
    table = _translit_dictionary(lookup)

    def _one(m):
        w = m.group(0).lower()
        out = table.get(w) or _rule_translit(w, lookup)
        if via_dev:
            return _fold_from_dev(out, script)
        # A script with its own tables keeps their spelling, but never their
        # stray Devanagari — see _clamp_stray_dev. No-op for 'dev' itself and
        # for the 116k Bengali entries that are already clean.
        return _clamp_stray_dev(out, script)
    return _LATIN_RUN.sub(_one, text)


# Language code → script the transcript should be rendered in. Every Indic
# language the form offers is listed, in both its ISO 639-1 and 639-3 spelling.
# Absent codes map to None, meaning "leave Latin words alone" — English, where
# converting would be plainly wrong, and Urdu, whose Perso-Arabic script is not
# laid out in parallel with the Indic blocks and so cannot be reached from the
# Devanagari dictionary. Urdu needs tables of its own before it can be listed.
_LANG_SCRIPT = {
    "hi": "dev", "hin": "dev", "mr": "dev", "mar": "dev",
    "ne": "dev", "nep": "dev", "sa": "dev", "san": "dev",
    "bn": "beng", "ben": "beng", "as": "beng", "asm": "beng",
    "pa": "guru", "pan": "guru", "gu": "gujr", "guj": "gujr",
    "or": "orya", "ori": "orya", "ta": "taml", "tam": "taml",
    "te": "telu", "tel": "telu", "kn": "knda", "kan": "knda",
    "ml": "mlym", "mal": "mlym",
}


def script_for_lang(code):
    """Target script for a language code, or None when there is nothing to
    convert into. Returns the sentinel 'auto' when no language is pinned — auto
    defers the decision to _dominant_script(), which reads it off the transcript
    itself."""
    c = (code or "").strip().lower()
    if is_auto_lang(c):
        return "auto"
    return _LANG_SCRIPT.get(c)


def _dominant_script(raw_words):
    """Script the bulk of a transcript is already written in, or None.

    Used for auto-detect runs, where no language_code was sent and Scribe may
    hand back Devanagari (or Bengali) with a few stray Latin words. Requires a
    clear majority so a genuinely English transcript is never Indic-ised.

    The majority is counted over EVERY Indic script in the transcript, not only
    over the ones that can be transliterated into. Counting a subset made any
    amount of Devanagari a 100% majority: a reel in some other script that
    quotes two Sanskrit words in Devanagari would have its stray English written
    in Devanagari, inside cues that are not Devanagari from end to end. With
    every script counted, that transcript has no majority and its Latin words
    are left alone.

    Auto-detect reaches whatever _TRANSLIT_SCRIPTS covers, so it stays in step
    with a pinned language rather than being a second, narrower rule. Urdu is
    still excluded, since it has no tables."""
    counts = {}
    for w in raw_words:
        s = _token_script(getattr(w, "text", "") or "")
        if s:
            counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values())
    if total < 3:
        return None
    # Devanagari wins a dead heat, as it did when it and Bengali were the only
    # two scripts counted.
    top = max(counts, key=lambda s: (counts[s], s == "dev"))
    if top not in _TRANSLIT_SCRIPTS:
        return None
    return top if counts[top] >= 0.6 * total else None


# ── Function words ──────────────────────────────────────────────────────────
# BIND_BACK completes the word before it, so a cue may never open with one.
# BIND_FWD opens the clause after it, so a cue should not end on one. Both are
# per language, unioned per script because auto-detect often cannot say which
# language a token is. The tables, and the linguistics behind them, are in
# languages/ — see its __init__.py.
_FW_STRIP = _scripts.FW_STRIP
# Characters to delete inside a token before the lookup, so that the spelling
# variants Scribe produces all reach the same table entry. Built from codepoints
# because most of them are invisible in an editor:
#   • zero-width joiners and bidi marks — emitted inconsistently around
#     Devanagari, Bengali and Urdu words;
#   • the Arabic vowel points and superscript alef, which Urdu normally omits but
#     which do appear;
#   • the nukta of every Indic script. This one is visible, and it is dropped
#     because transcripts are inconsistent about it — "पड़ेगा" also arrives as
#     "पडेगा", "হয়" as "হয". Dropping it on both sides of the comparison (the
#     tables are normalized through this same function) only ever adds matches,
#     and no function word in any of the tables is distinguished from a content
#     word by its nukta alone.
# Marks deleted inside a token before a lookup, so the spelling variants
# Scribe produces all reach the same entry — see languages/scripts.py.
_FW_IGNORE = _scripts.FW_IGNORE


def _norm_fw(token):
    """Normalize a token for a function-word lookup: NFC (which also decomposes
    the precomposed nukta letters), no surrounding punctuation, and none of the
    marks in _FW_IGNORE."""
    t = unicodedata.normalize("NFC", token.strip()).strip(_FW_STRIP)
    if any(ch in _FW_IGNORE for ch in t):
        t = "".join(ch for ch in t if ch not in _FW_IGNORE)
    return t


_BIND_BACK_RAW = languages.BIND_BACK_RAW

_BIND_FWD_RAW = languages.BIND_FWD_RAW

# Language table key → script id, so a language hint is only trusted for tokens
# actually written in that language's script.
_FW_LANG_SCRIPT = languages.FW_LANG_SCRIPT

# ISO 639-1 / 639-3 spellings the UI and the Resolve side may send.
_FW_LANG_ALIAS = languages.FW_LANG_ALIAS

_EMPTY_FW = frozenset()


def _freeze_fw(raw):
    """(per-language raw tuples) → (per-language sets, per-script unions)."""
    by_lang, by_script = {}, {}
    for lang, words in raw.items():
        s = frozenset(_norm_fw(w) for w in words)
        by_lang[lang] = s
        sc = _FW_LANG_SCRIPT[lang]
        by_script[sc] = by_script.get(sc, frozenset()) | s
    return by_lang, by_script


_BIND_BACK_BY_LANG, _BIND_BACK_BY_SCRIPT = _freeze_fw(_BIND_BACK_RAW)
_BIND_FWD_BY_LANG,  _BIND_FWD_BY_SCRIPT  = _freeze_fw(_BIND_FWD_RAW)


def _fw_lookup(token, by_lang, by_script, lang):
    """Is ``token`` in the given function-word table?

    Uses ``lang``'s own table when a language is pinned AND the token is written
    in that language's script; otherwise the union for the token's script, which
    is what auto-detect and code-switched transcripts need."""
    t = _norm_fw(token)
    if not t:
        return False
    sc = _token_script(t)
    if sc is None:
        return False
    key = _FW_LANG_ALIAS.get((lang or "").strip().lower())
    if key and _FW_LANG_SCRIPT.get(key) == sc:
        return t in by_lang.get(key, _EMPTY_FW)
    return t in by_script.get(sc, _EMPTY_FW)


def _binds_back(token, lang=None):
    """True when ``token`` grammatically completes the word before it — an
    auxiliary, copula, postposition, case marker or enclitic particle. Such a
    word must never open a cue, nor sit alone in one."""
    return _fw_lookup(token, _BIND_BACK_BY_LANG, _BIND_BACK_BY_SCRIPT, lang)


def _binds_fwd(token, lang=None):
    """True when ``token`` opens the clause that follows it — a conjunction,
    subordinator or relative pronoun. A cue should not end on one."""
    return _fw_lookup(token, _BIND_FWD_BY_LANG, _BIND_FWD_BY_SCRIPT, lang)


# ── Clause ends the function-word tables cannot see ─────────────────────────
# The Dravidian languages suffix the finite verb ending onto the stem, so a
# clause can end with no separate token to mark it and the BIND tables see
# nothing. A finite verb form ends its clause, which makes the boundary after
# one a real clause boundary. Suffixes, and why they are as long as they are,
# live in the verb-final languages' own modules — see languages/__init__.py.
_VERB_END_RAW = languages.VERB_END_RAW
_VERB_END = {sc: tuple(unicodedata.normalize("NFC", s) for s in sfx)
             for sc, sfx in _VERB_END_RAW.items()}


def _ends_clause(token, lang=None):
    """True when ``token`` is a finite verb form closing its own clause.

    Only consulted for the verb-final scripts in _VERB_END; every other script
    writes the same information as separate tokens the BIND tables already see.

    A word in the bind-forward table is never a clause end however it happens to
    be spelled — Kannada "ಆದರೆ" ("but") ends in the same -ರೆ as the finite
    "ಮಾಡುತ್ತಾರೆ", and it opens the clause that follows rather than closing the
    one before."""
    t = _norm_fw(token)
    if not t:
        return False
    sfx = _VERB_END.get(_token_script(t))
    if not sfx:
        return False
    if _binds_fwd(t, lang):
        return False
    return any(t.endswith(s) for s in sfx)


# Max gap (seconds) between the previous cue's end and a lone bind-back word's
# start for the two to be considered the same phrase. Sentence-final auxiliaries
# follow their head almost immediately; a large gap means a real pause, so we
# leave the word alone rather than glue across sentences.
_GLUE_MAX_GAP = 1.2

# Two consecutive cues separated by less than this much silence are made
# contiguous (_sanitize_cues): the earlier cue's end is pushed up to the later
# one's start, so Resolve's subtitle track shows an unbroken run of captions
# instead of caption / blank / caption flicker at every inter-word pause. Word
# end-times from the ASR stop where the word stops, and those sub-second holes
# were showing up as gaps on the timeline. Anything longer is a real pause and
# is left alone — a caption should not sit on screen through silence. This is
# the same 1s threshold the caption importer uses when it joins clips
# (joinThreshold in audio_to_srt.py).
_GAP_CLOSE_MAX = 1.0

# ── Pause-aware splitting ────────────────────────────────────────────────────
# A silence between two words is where the speaker actually breathed/paused —
# the most natural place for a subtitle boundary. What counts as a silence,
# though, is a property of the SPEAKER, not a constant: fixed thresholds split
# a slow, deliberate delivery mid-phrase (every measured gap looks like a pause)
# and never split rapid speech at all (no gap ever reaches the constant, so
# every boundary ends up chosen by the character budget instead). So the
# thresholds are measured from the transcript itself — see _pause_profile.
#
# These two remain the defaults for inputs too short to measure (< _PAUSE_MIN_N
# gaps) and the anchors the measured values are clamped against.
_PAUSE_SPLIT = 0.35   # gap that closes a cue outright
_PAUSE_MIN   = 0.12   # gap big enough to be worth preferring over an arbitrary cut
_PAUSE_FLOOR = 0.16   # a measured split threshold never drops below this …
_PAUSE_CEIL  = 0.80   # … nor rises above it
_PAUSE_MIN_N = 8      # gaps needed before the measurement is trusted


class _Pauses:
    """Pause thresholds for one transcript.

    ``split`` — a gap this wide closes the cue: real silence in the audio.
    ``hint``  — a gap this wide is meaningful enough to prefer as a cut point
                when the character/duration budget forces a split anyway.
    """
    __slots__ = ("split", "hint")

    def __init__(self, split, hint):
        self.split = split
        self.hint = hint


def _percentile(sorted_vals, q):
    """Linear-interpolated percentile of an already-sorted list."""
    if not sorted_vals:
        return 0.0
    k = q * (len(sorted_vals) - 1)
    lo = int(math.floor(k))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _pause_profile(words):
    """Measure what a pause means for THIS speaker, from the word timings.

    The median inter-word gap is the delivery's baseline rhythm and the 85th
    percentile is what a wide gap looks like for it. A cue-closing pause has to
    clear both: ``max(p85, 2 × median)``. The p85 term is what adapts to speed —
    it drops with rapid speech so real breaths are still found, and rises with a
    slow delivery so ordinary between-word spacing stops being mistaken for a
    pause. The 2 × median term is the guard for genuinely continuous speech,
    where p85 ≈ median and splitting at p85 would be arbitrary: doubling the
    baseline pushes the threshold above every gap present, so no pause split
    fires and the linguistic/budget path decides instead.

    Clamped to [_PAUSE_FLOOR, _PAUSE_CEIL] so neither end of the range produces
    an absurd threshold, and short inputs (fewer than _PAUSE_MIN_N gaps, too
    little to measure) keep the fixed defaults."""
    gaps = []
    prev_end = None
    for w in words:
        if not (getattr(w, "text", "") or "").strip():
            continue
        ws = float(getattr(w, "start", 0) or 0)
        we = float(getattr(w, "end", 0) or 0)
        if prev_end is not None:
            gaps.append(max(0.0, ws - prev_end))   # ASR overlap → 0, not negative
        prev_end = we
    if len(gaps) < _PAUSE_MIN_N:
        return _Pauses(_PAUSE_SPLIT, _PAUSE_MIN)
    gaps.sort()
    baseline = _percentile(gaps, 0.50)
    wide = _percentile(gaps, 0.85)
    split = min(max(max(wide, 2.0 * baseline), _PAUSE_FLOOR), _PAUSE_CEIL)
    return _Pauses(split, min(max(0.35 * split, 0.04), split))


# ── Boundary scoring ─────────────────────────────────────────────────────────
# When a budget (characters, duration, reading speed, word count) forces the cue
# to close, every possible cut point is scored and the best one wins. Weights
# are in arbitrary points, ordered so that:
#   • a sentence terminator beats everything else;
#   • a wide silence beats a clause boundary, and a clause boundary beats a
#     narrow silence;
#   • a cut with NO support at all — no punctuation, no audible gap — is a
#     mid-phrase break, the split that reads as wrong however well the budgets
#     are respected, so it is penalised more than any single bonus is worth;
#   • leaving a phrase-completing word to open the next cue is bad (_P_BIND_BACK)
#     but still better than pulling a content word out of this cue with nothing
#     in the audio or the punctuation to justify it (_P_ARBITRARY). That ordering
#     is what stops the splitter from carrying a cue's last word into the next
#     cue unless the word genuinely belongs after the boundary.
_W_SENTENCE  = 6.0    # previous word ends a sentence
_W_CLAUSE    = 3.0    # previous word ends a clause
_W_PAUSE     = 4.0    # × min(gap / pauses.split, 1.5)
_W_FILL      = 2.0    # × how much of the cue's budget is used
_P_BIND_BACK = 2.5    # next cue would open with a phrase-completing word
_P_BIND_FWD  = 1.5    # this cue would end on a clause-opening word
_P_ARBITRARY = 4.0    # neither punctuation nor a pause at this cut


def _cut_supported(buf, cut, next_start, pauses, lang=None):
    """Is there anything at this boundary to justify it?

    True when the word before the cut ends a sentence or a clause — in
    punctuation, or, in the verb-final languages, in a finite verb ending that
    closes the clause without any punctuation at all — or when there is an
    audible gap after it. A cut with none of the three is invisible in both the
    text and the audio — the caller must not carry words across it, because
    every word moved over such a boundary is a word that reads as belonging to
    the cue it just left."""
    prev = buf[cut - 1]
    nxt_start = buf[cut][1] if cut < len(buf) else next_start
    return (_ends_with(prev[4], _STRONG_END)
            or _ends_with(prev[4], _WEAK_END)
            or _ends_clause(prev[4], lang)
            or (nxt_start - prev[2]) >= pauses.hint)


def _clitic_chain_start(buf, next_text, lang):
    """Index in ``buf`` of the head of the phrase ``next_text`` completes.

    When the word about to be added binds back it belongs with the word before
    it — and that word may bind back in turn, so the chain is walked to the
    content word heading it: "समझा" of "समझा रहा हूँ", "বলতে" of "বলতে পারি",
    "بڑھیں" of "بڑھیں گے". If the cue must be closed and the incoming word
    cannot stay in it, this is the only cut that keeps the phrase whole.

    Returns len(buf) when the incoming word does not bind back (nothing to keep
    together), or 0 when the entire buffer is part of the chain."""
    if not _binds_back(next_text, lang):
        return len(buf)
    j = len(buf)
    while j > 0 and _binds_back(buf[j - 1][4], lang):
        j -= 1
    return max(j - 1, 0)      # the content word at the head goes along too


def _best_cut(buf, next_text, next_start, cap, pauses, lang):
    """Where to close the cue held in ``buf``.

    ``buf`` holds (text, start, end, speaker, raw_text) per word; ``next_text``
    / ``next_start`` describe the word that would open the following cue if the
    whole buffer were flushed. Returns j in 1..len(buf): the cue keeps buf[:j]
    and buf[j:] carries over, so the return value is always progress.

    Candidates are scored on what the language and the audio say about the
    boundary rather than on where the budget happened to run out — see the
    weights above. Ties go to the later cut, which keeps the cue as full as the
    budget allows and leaves as little as possible to carry over."""
    best_j, best_score = len(buf), None
    chars = 0
    for j in range(1, len(buf) + 1):
        prev = buf[j - 1]
        chars += _vlen(prev[0]) + (1 if chars else 0)
        if j < len(buf):
            nxt_text, nxt_start = buf[j][4], buf[j][1]
        else:
            nxt_text, nxt_start = next_text, next_start
        gap = max(0.0, nxt_start - prev[2])

        strong = _ends_with(prev[4], _STRONG_END)
        weak = _ends_with(prev[4], _WEAK_END) or _ends_clause(prev[4], lang)
        score = _W_SENTENCE if strong else (_W_CLAUSE if weak else 0.0)
        score += _W_PAUSE * min(gap / pauses.split, 1.5)
        if not _cut_supported(buf, j, next_start, pauses, lang):
            score -= _P_ARBITRARY
        if _binds_back(nxt_text, lang):
            score -= _P_BIND_BACK
        if _binds_fwd(prev[4], lang):
            score -= _P_BIND_FWD
        if cap > 0:
            score += _W_FILL * min(chars / float(cap), 1.0)

        if best_score is None or score >= best_score:
            best_score, best_j = score, j
    return best_j


def _append_word(cue_text, word, max_chars, max_lines):
    """Append ``word`` to an already-wrapped cue without violating the
    char/line budget.

    Adds to the last line when it still fits, else starts a new line while one
    is available, else returns None — there is nowhere left to put the word
    within budget, so the caller must not force the merge (unlike wrap(),
    which is building a single cue from scratch and has no "leave it out"
    option, here the word already has a perfectly good home: staying in its
    own cue)."""
    lines = cue_text.split("\n")
    last = lines[-1]
    if not last:
        lines[-1] = word
    elif _vlen(last) + 1 + _vlen(word) <= max_chars:
        lines[-1] = last + " " + word
    elif len(lines) < max_lines:
        lines.append(word)
    else:
        return None
    return "\n".join(lines)


def _reattach_clitics(cues, max_chars, max_lines, max_words=0, max_secs=None,
                      pauses=None, lang=None):
    """Move a cue's leading phrase-completing word back onto the previous cue.

    No cue may OPEN with a word that grammatically finishes the phrase it was cut
    away from — "है", "ছিল", "ஆகும்", "ہے", "ਹੈ", "છે" and the postpositions /
    case markers alongside them. _best_cut already avoids creating such a
    boundary, but two things can still produce one: a budget so tight that every
    alternative is worse, and the remap path, which builds cues per timeline clip
    and so never sees the neighbouring clip's cues. This pass is the final check
    over the finished list.

    A word is moved only when it is still the same phrase as what precedes it:
      • the two cues touch in time — a lone auxiliary may lag its head by up to
        _GLUE_MAX_GAP, but a word pulled off the head of a real (multi-word) cue
        may not cross a measured pause, because a cue that starts after a genuine
        silence was split there for a reason;
      • both sides are the same script, so the cue keeps one font; and
      • the word still fits the receiving cue's character, line, word AND
        duration budget — a cue that ends later also stays on screen longer, so
        without the duration check a single moved word can push a cue past
        max_secs (which is how a two-word Bengali cue came out 1.35s long against
        a 1.07s limit).
    Otherwise it stays where it is. Nothing is ever dropped, duplicated or
    re-timed: word order and every word's own timestamps are untouched, only
    which cue draws it changes. Cues are re-numbered 1-based afterwards so
    downstream SRT numbering stays correct."""
    if pauses is None:
        pauses = _Pauses(_PAUSE_SPLIT, _PAUSE_MIN)
    out = []
    for cue in cues:
        _, s, e, text, words = cue
        while out and words and _binds_back(words[0][0], lang):
            pidx, ps, pe, ptext, pwords = out[-1]
            head = words[0]
            gap = head[1] - pe
            limit = _GLUE_MAX_GAP if len(words) == 1 else pauses.split
            if (_word_script(head[0]) != _word_script(ptext)
                    or not (-0.1 <= gap <= limit)
                    or (max_words > 0 and len(pwords) >= max_words)
                    or (max_secs is not None and head[2] - ps > max_secs)):
                break
            merged = _append_word(ptext, head[0], max_chars, max_lines)
            if merged is None:
                break
            out[-1] = (pidx, ps, head[2], merged, pwords + [head])
            words = words[1:]
            if not words:
                break                    # whole cue absorbed — nothing left
            s = words[0][1]
            text = wrap(" ".join(w[0] for w in words), max_chars, max_lines, lang)
        if words:
            out.append((0, s, e, text, words))
    return [(i + 1, s, e, t, w) for i, (_, s, e, t, w) in enumerate(out)]


# A cue holding less than this much of its own character budget reads as an
# orphan — one stray word flashing between two full ones. Measured on a 15-char
# single-line reel, where the splitter emitted उस, करता, खाना and हफ़्तों as cues
# of their own while their phrases sat in the cue next door.
#
# Capped in absolute characters as well, because the fraction alone is wrong at
# the other end of the range: under a 300-character budget a 7-character cue is
# 2% "full" and not an orphan at all — it is a short utterance the speaker set
# off with silence, and tidying it away would undo the pause boundary that
# earned it.
_RUNT_FRACTION = 0.40
_RUNT_MAX_CHARS = 8


def _rebalance_cues(cues, max_chars, max_lines, max_secs, max_words=0,
                    pauses=None, lang=None):
    """Even out a runt cue against the one beside it.

    _best_cut scores a boundary in isolation: it decides where to CLOSE the
    current cue and never sees what the remainder will look like, so a wide
    enough pause after the first word justifies cutting there however little is
    left behind. Three other paths in build_cues — a pause boundary, a sentence
    terminator, the final flush — emit a cue without consulting it at all. Any
    of the four can leave one word standing alone, which breaks no budget and
    still reads as a mistake.

    Two repairs, tried in order on each adjacent pair:
      1. Merge, when the two together still fit inside one cue's budget AND
         nothing justified the boundary in the first place. A cue split at
         punctuation or at a measured silence was split for a reason; being
         short is not grounds to undo it.
      2. Move the boundary LEFT, when they do not fit — pull words out of the
         second cue into the first until the pair is even.

    Only left. Moving a word the other way, out of the full cue into the short
    one, shrinks the first cue and can leave it with room the word that just
    left would have fitted in — an unsupported boundary that the budget no
    longer excuses, which is precisely the "last word jumped to the next
    subtitle" fault. Pulling words leftward cannot create that: the receiving
    cue only grows.

    Refused unless the result is legal on every budget and the grammar allows
    the new boundary — no cue may open with a phrase-completing word or close
    on a clause-opening one, the defect _reattach_clitics exists to clean up
    and this pass must not reintroduce. Once both sides clear the runt floor, a
    boundary with punctuation or an audible gap behind it wins over a
    marginally more even one.

    Word order and every word's timestamps are untouched; only which cue draws
    a word changes, and each cue's start/end are recomputed from the words it
    ends up with, so timings keep following the audio."""
    if not cues:
        return cues
    if pauses is None:
        pauses = _Pauses(_PAUSE_SPLIT, _PAUSE_MIN)
    cap = max_chars * max_lines
    floor = min(cap * _RUNT_FRACTION, _RUNT_MAX_CHARS)

    def text_of(words):
        return " ".join(w[0] for w in words)

    def raw_of(word):
        """The word with its punctuation. build_cues keeps it alongside the
        display text so this pass can still see a sentence terminator when
        include_punct has stripped it from the screen; cues arriving from
        anywhere else carry four fields and the display text is all there is."""
        return word[4] if len(word) > 4 else word[0]

    def legal(words):
        return (bool(words)
                and (max_words <= 0 or len(words) <= max_words)
                and (max_secs is None
                     or words[-1][2] - words[0][1] <= max_secs)
                and _vlen(text_of(words)) <= cap)

    def as_cue(words):
        return (0, words[0][1], words[-1][2],
                wrap(text_of(words), max_chars, max_lines, lang), words)

    def speaker(words):
        for w in words:
            if len(w) > 3 and w[3] is not None:
                return w[3]
        return None

    out = []
    for cue in cues:
        words = list(cue[4]) if len(cue) > 4 else []
        if not words or not out or not out[-1][4]:
            out.append(cue if not words else as_cue(words))
            continue

        prev = list(out[-1][4])
        a_len, b_len = _vlen(text_of(prev)), _vlen(text_of(words))
        joined = prev + words

        # Only ever triggered by a runt. A pair that is already well balanced
        # was split where the audio and the grammar said to; leave it alone.
        if min(a_len, b_len) >= floor:
            out.append(as_cue(words))
            continue

        # A cue may not mix speakers or scripts, and a silence wide enough to
        # be a new utterance is a boundary in its own right — not something to
        # tidy away because one side came out short.
        ps, bs = speaker(prev), speaker(words)
        if ((ps is not None and bs is not None and ps != bs)
                or _word_script(text_of(prev)) != _word_script(text_of(words))
                or words[0][1] - prev[-1][2] > _GLUE_MAX_GAP):
            out.append(as_cue(words))
            continue

        # A sentence terminator may only ever sit at the END of a cue.
        # build_cues closes on one deliberately (rule 3: do not merge unrelated
        # sentences), and evening out a short pair must not undo that by
        # carrying the next sentence back across it.
        if any(_ends_with(raw_of(w), _STRONG_END) for w in joined[:-1]):
            out.append(as_cue(words))
            continue

        # Was there a reason for the boundary? Punctuation or a measured
        # silence means the splitter put it there on purpose.
        gap = words[0][1] - prev[-1][2]
        justified = (_ends_with(raw_of(prev[-1]), _STRONG_END)
                     or _ends_with(raw_of(prev[-1]), _WEAK_END)
                     or _ends_clause(raw_of(prev[-1]), lang)
                     or gap >= pauses.split)

        # 1. Merge, when the pair fits one cue and nothing earned the split.
        if not justified and legal(joined):
            out[-1] = as_cue(joined)
            continue

        # 2. Otherwise pull words leftward, but only to rescue a short FIRST
        #    cue — see the docstring on why the mirror image is unsafe. Rank by
        #    how much sits on the thinner side, and stop caring once both sides
        #    clear the floor: past that point a boundary the audio or the
        #    punctuation agrees with beats another character of evenness.
        if a_len >= floor:
            out.append(as_cue(words))
            continue
        best, best_key = None, (min(a_len, b_len), False, min(a_len, b_len))
        for j in range(len(prev) + 1, len(joined)):
            left, right = joined[:j], joined[j:]
            if not legal(left) or not legal(right):
                continue
            if _binds_back(right[0][0], lang) or _binds_fwd(left[-1][0], lang):
                continue
            lo = min(_vlen(text_of(left)), _vlen(text_of(right)))
            supported = (right[0][1] - left[-1][2]) >= pauses.hint
            key = (min(lo, floor), supported, lo)
            if key > best_key:
                best, best_key = (left, right), key
        if best:
            out[-1] = as_cue(best[0])
            words = best[1]
        out.append(as_cue(words))

    return [(i + 1, s, e, t, w) for i, (_, s, e, t, w) in enumerate(out)]


def build_cues(words, max_chars, max_lines, max_secs, include_punct="1",
               cps=0.0, max_words=0, lang=None):
    """Group word-timed transcription tokens into SRT cues.

    Chunking rules:
      1. Split at natural boundaries. Every candidate cut is scored (_best_cut)
         on the sentence/clause punctuation of the word before it, the width of
         the silence at it measured against this speaker's own rhythm, and the
         grammar of the words on either side — so the boundary lands where the
         phrase ends, not where the character budget ran out.
      2. Never split a phrase across cues: a cue never opens with a word that
         completes the phrase before it (है / ছিল / ஆகும் / ہے / ਹੈ, and the
         postpositions and case markers written as separate words), and never
         closes on a word that opens the next clause (और / কিন্তু / ஆனால் / اور)
         unless the audio says otherwise.
      3. Do not merge unrelated sentences — once a sentence terminator is
         emitted, close the cue at that point rather than carrying the next
         sentence into the same chunk.
      4. cps > 0 caps reading speed (characters per second, AutoSubs-style):
         a cue that would exceed it is split early at the best boundary.
      5. A cue never mixes speakers: a diarization speaker change is a hard
         boundary, same as a script change.

    Rules 1 and 2 work for every supported language: punctuation covers the
    Indic danda and the Urdu full stop as well as the Latin set, pause widths are
    measured rather than assumed, and the grammar tables are keyed by the token's
    script so they apply without a language being pinned. Passing ``lang`` (an
    ISO 639-1/639-3 code) narrows the tables to that one language, which matters
    only where two languages share a script and disagree about a word.

    Word order and word timings are never altered: cues are built by slicing the
    word stream in order, so every input word appears in exactly one cue, in the
    order it was spoken, with the timestamps it came in with.
    """
    cues = []
    idx = 1
    # (display_text, start, end, speaker, raw_text) per buffered word. raw_text
    # keeps the punctuation even when include_punct strips it from the display
    # text — the sentence structure is still the best split signal there is, and
    # throwing it away before looking for a boundary is what left the
    # no-punctuation mode splitting blind.
    buf = []
    start = None
    end = None
    cur_spk = None  # diarization speaker of the words currently buffered
    cap = max_chars * max_lines
    pauses = _pause_profile(words)

    def _flush_at(cut):
        """Emit a cue for buf[:cut]; return remaining buf[cut:].

        Each cue is (idx, start, end, wrapped_text, words) where words is the
        list of (word_text, word_start, word_end, speaker) it was built from —
        retained so the caller can emit per-word timing in the sidecar."""
        nonlocal idx
        if cut <= 0 or not buf:
            return buf
        head = buf[:cut]
        text = " ".join(entry[0] for entry in head)
        cue_text = wrap(text, max_chars, max_lines, lang)
        # Five fields, not four: the raw text keeps its punctuation, which
        # _rebalance_cues needs to see a sentence terminator that include_punct
        # has stripped from the display text. Trimmed back to four on the way
        # out of build_cues — everything downstream expects four.
        cues.append((idx, head[0][1], head[-1][2], cue_text,
                     [entry[:5] for entry in head]))
        idx += 1
        return buf[cut:]

    def _phrase_can_move(at, end_time):
        """Would buf[at:] plus the incoming word fit in a cue of their own?

        Moving a phrase forward to keep it whole is only worth doing if the cue
        that receives it can hold it. When it cannot, the move just relocates
        the breach — a Hindi "दुनिया में" whose two words are 1.44s apart cannot
        share a cue under a 0.77s limit however it is arranged, so the duration
        budget wins and the postposition opens the next cue instead."""
        return ((max_words <= 0 or len(buf) - at + 1 <= max_words)
                and end_time - buf[at][1] <= max_secs)

    def _cue_fits(at):
        """Would buf[:at] be a legal cue on its own, duration-wise?"""
        return buf[at - 1][2] - buf[0][1] <= max_secs

    for w in words:
        raw = unicodedata.normalize("NFC", (getattr(w, "text", "") or "").strip())
        wt = raw
        if include_punct == "0":
            wt = _PUNCT_OFF_RE.sub("", wt).strip()
        ws = float(getattr(w, "start", 0) or 0)
        we = float(getattr(w, "end", 0) or 0)
        if not wt:
            continue

        if start is None:
            start = ws

        # Speaker boundary (diarization): a cue must never mix speakers.
        w_spk = getattr(w, "speaker", None)
        if buf and w_spk is not None and cur_spk is not None and w_spk != cur_spk:
            buf = _flush_at(len(buf))
            start = ws
            end = we
        if w_spk is not None:
            cur_spk = w_spk

        # Script boundary (Bengali ↔ Devanagari): a cue must be single-script
        # so the Resolve-side importer can assign exactly one font per cue.
        # Flush the whole buffer the moment the incoming word switches script.
        w_script = _word_script(wt)
        if buf and w_script:
            b_script = _buf_script(buf)
            if b_script and w_script != b_script:
                buf = _flush_at(len(buf))
                start = ws
                end = we

        # Pause boundary: real silence in the audio closes the cue, so the
        # subtitle disappears with the speech and the next one appears exactly
        # when the speaker resumes — cue timing tracks the audio, not the
        # character budget. What counts as silence is measured per transcript
        # (_pause_profile), which is what makes this work at both ends of the
        # speed range: a fixed threshold splits slow, deliberate delivery
        # mid-phrase and finds nothing at all in rapid speech.
        #
        # A phrase-completing word never starts a cue, so a pause before one
        # does not split — unless the gap is so long (> _GLUE_MAX_GAP) that it is
        # clearly a new utterance rather than the speaker's own hesitation.
        if buf and end is not None:
            gap = ws - end
            if gap >= pauses.split and (not _binds_back(raw, lang)
                                        or gap > _GLUE_MAX_GAP):
                buf = _flush_at(len(buf))
                start = ws
                end = we

        prospective_text = " ".join(
            [entry[0] for entry in buf] + [wt])
        too_long = _vlen(prospective_text) > cap
        too_long_dur = (we - start) > max_secs and bool(buf)
        # Reading-speed cap: past a settling window of 0.5s (so one quick word
        # at cue start does not trip it), split when chars/sec would exceed cps.
        dur = we - start
        too_fast = (cps > 0 and bool(buf) and dur >= 0.5
                    and _vlen(prospective_text) / dur > cps)
        # Hard word cap (animated "one hook per clip" style): once the buffer
        # already holds max_words words, the incoming word starts a new cue.
        too_many_words = (max_words > 0 and len(buf) >= max_words)

        # Only split when there is a buffer to split. A single word longer than
        # the whole character budget (e.g. a long Devanagari compound) has
        # nothing to cut — it just becomes its own cue rather than crashing the
        # boundary search on an empty buffer.
        if (too_long or too_long_dur or too_fast or too_many_words) and buf:
            # A budget is spent, so the cue has to close somewhere in the
            # *current* buffer (the incoming word is not part of it yet). Score
            # every candidate and take the best — punctuation, measured pause
            # width, grammar on both sides, and how full the cue would be, all
            # weighed together instead of the old fixed cascade of "last strong
            # boundary, else last weak one, else widest gap, else wherever the
            # budget ran out".
            #
            # The result is always 1..len(buf), so the buffer always shrinks and
            # the loop always makes progress.
            cut = _best_cut(buf, raw, ws, cap, pauses, lang)
            chain = _clitic_chain_start(buf, raw, lang)

            # (i) A word may only be carried into the next cue across a boundary
            # that exists: punctuation, an audible gap, or the head of the phrase
            # the incoming word completes (``chain``). When the best cut has none
            # of the three, the whole buffer is flushed instead and the cue keeps
            # its own last word.
            #
            # This is the guarantee the old walk-back broke. It stepped the cut
            # backwards whenever the next cue would have opened with an auxiliary
            # — one word per glue word found, however far that reached — so a
            # perfectly good final word was pushed to the head of the next
            # subtitle with nothing in the audio or the grammar marking a
            # boundary there. That is the reported "last word jumps to the next
            # subtitle" fault.
            #
            # Two things override the guard. A cut at the head of a phrase is
            # allowed (that is what keeps "व्यवस्था के" together) provided the
            # phrase fits the cue it moves to. And flushing the whole buffer is
            # only an option while that buffer is still a legal cue: when the
            # split was forced by max_secs, holding everything back would emit
            # the over-long cue the split exists to prevent, so the early cut
            # stands and the duration budget wins.
            if cut < len(buf) and not _cut_supported(buf, cut, ws, pauses, lang):
                if (not (cut == chain and _phrase_can_move(chain, we))
                        and _cue_fits(len(buf))):
                    cut = len(buf)

            # (ii) The phrase still has to stay whole, in order of preference:
            #   1. keep the incoming word in THIS cue, one word over budget —
            #      nothing moves at all;
            #   2. failing that (a budget is genuinely spent), close the cue at
            #      the head of the phrase so the whole phrase moves together;
            #   3. failing that too (the buffer IS the phrase), let the word open
            #      the next cue — there is nothing better left.
            #
            # Deferring has to stay bounded: with a run of such words the cue
            # would defer on every iteration and sail past max_words / max_secs
            # (20 words at max_words=15). So it is allowed only while the cue is
            # still within its other budgets. The character test looks at the
            # buffer without the incoming word, so a deferral may overshoot by
            # one word but never compounds: the next word finds buf over cap and
            # splits.
            buf_chars = _vlen(prospective_text) - _vlen(wt) - 1
            may_defer = (not too_many_words and not too_long_dur
                         and buf_chars <= cap)
            real_boundary = (cut < len(buf)
                             and _cut_supported(buf, cut, ws, pauses, lang))
            if _binds_back(raw, lang) and not real_boundary:
                if may_defer:
                    cut = 0
                elif (cut == len(buf) and chain > 0
                        and _phrase_can_move(chain, we)):
                    cut = chain

            buf = _flush_at(cut)
            # Whatever is left has to be able to hold the incoming word. A cut
            # chosen for its linguistics or its pause can leave a tail that,
            # once this word joins it, is over max_secs again — and nothing
            # would notice until the word after that, by which time the
            # over-long cue has already been emitted. Flush the tail too, so
            # the incoming word starts a cue of its own.
            if buf and we - buf[0][1] > max_secs:
                buf = _flush_at(len(buf))
            start = buf[0][1] if buf else ws
            end   = buf[-1][2] if buf else we

        buf.append((wt, ws, we, w_spk, raw))
        end = we

        # Rule 3 — a sentence terminator closes the cue right here, so the next
        # sentence does not get merged with this one. Tested on the raw token, so
        # this still works when include_punct has stripped the terminator from
        # the text that will be displayed.
        if _ends_with(raw, _STRONG_END):
            buf = _flush_at(len(buf))
            start = None
            end = None

    if buf:
        _flush_at(len(buf))
    cues = _reattach_clitics(cues, max_chars, max_lines, max_words,
                             max_secs=max_secs, pauses=pauses, lang=lang)
    # Last, because it is the only pass that can see a finished cue next to its
    # neighbour and judge the pair. Deliberately NOT run again after the remap
    # in build_and_remap_cues: cues there are already timeline-shifted and the
    # neighbour may belong to a different clip, so evening the two out would
    # move a word across an edit point.
    cues = _rebalance_cues(cues, max_chars, max_lines, max_secs, max_words,
                           pauses=pauses, lang=lang)
    return [(i, s, e, t, [w[:4] for w in ws])
            for i, s, e, t, ws in cues]


def to_srt(cues):
    # Dummy entry at t=0 forces Resolve to anchor the subtitle clip at the
    # timeline start frame. Without it, Resolve places the clip at the first
    # real cue's time and uses clip-relative offsets, shifting every subtitle
    # forward by first_cue_time (typically ~0.1-0.5s).
    parts = ["1\n00:00:00,000 --> 00:00:00,001\n \n"]
    for cue in cues:
        i, s, e, t = cue[0], cue[1], cue[2], cue[3]
        parts.append("%d\n%s --> %s\n%s\n" % (i + 1, fmt_ts(s), fmt_ts(e), t))
    return "\n".join(parts)


def _cue_speaker(words):
    """The diarization speaker of a cue: first non-empty speaker among its
    words (cues are single-speaker, so the first is representative)."""
    for entry in words:
        spk = entry[3] if len(entry) > 3 else None
        if spk is not None and spk != "":
            return spk
    return None


def to_caption_sidecar(cues, fps, speaker_colors):
    """Serialize cues (with per-word timing + speaker) to a simple line-based
    format the Resolve-side importer parses without needing a JSON library. It
    reads it for the per-speaker cue colouring.

        FPS <rate>
        SPK <index> <#hexcolor> <style>          # 1-based, one per speaker
        SEG <start_s> <end_s> <speaker_index>    # speaker_index 0 = none
        WRD <start_s> <end_s> <word text...>     # words follow their SEG

    Segment text is the words joined by single spaces."""
    # Map raw diarization ids (e.g. "speaker_0") → 1-based speaker index in
    # first-appearance order, and assign each a colour from the palette.
    order = []
    seen = {}
    for cue in cues:
        spk = _cue_speaker(cue[4] if len(cue) > 4 else [])
        if spk is not None and spk not in seen:
            seen[spk] = len(order) + 1
            order.append(spk)

    lines = ["FPS %g" % fps]
    for idx, spk in enumerate(order, start=1):
        color = speaker_colors[(idx - 1) % len(speaker_colors)] if speaker_colors else "#FFFFFF"
        lines.append("SPK %d %s Fill" % (idx, color))

    for cue in cues:
        s, e = cue[1], cue[2]
        words = cue[4] if len(cue) > 4 else []
        spk = _cue_speaker(words)
        spk_idx = seen.get(spk, 0)
        lines.append("SEG %.3f %.3f %d" % (s, e, spk_idx))
        if words:
            for wt, ws, we, _ in words:
                clean = wt.replace("\n", " ").replace("\r", " ")
                lines.append("WRD %.3f %.3f %s" % (ws, we, clean))
        else:
            # No word-level data (shouldn't happen with Scribe) — fall back to
            # the whole cue text as one "word" spanning the cue.
            lines.append("WRD %.3f %.3f %s" % (s, e, cue[3].replace("\n", " ")))
    return "\n".join(lines) + "\n"


def read_clip_ranges(path):
    """Each line: src_start_frames src_end_frames tl_start_frames fps anchor_frame [src_path]

    The optional 6th field is the source media file for that clip (added so
    correction clips on the same track from a different file get transcribed
    too). Legacy 5-field rows are still accepted with src_path=None.
    """
    if not path or not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            # split with maxsplit=5 so the path (which may contain spaces) is
            # captured intact as the final field.
            parts = line.split(None, 5)
            if len(parts) < 5:
                continue
            src_start, src_end, tl_start, fps, anchor = parts[:5]
            src_path = parts[5].strip() if len(parts) == 6 else None
            out.append({
                "src_start_s": float(src_start) / float(fps),
                "src_end_s":   float(src_end)   / float(fps),
                "tl_start_s":  float(tl_start)  / float(fps),
                "anchor_s":    float(anchor)    / float(fps),
                "src_path":    src_path,
                "fps":         float(fps),
            })
    # Sort by timeline position so earlier-in-timeline clips get priority
    out.sort(key=lambda r: r["tl_start_s"])
    return out


def _clamp_words(words, s, e):
    """Confine every word's (start, end) to [s, e], preserving order and any
    extra fields (speaker). Nothing is ever dropped — the text is still on
    screen, so it still needs a timestamp inside the cue.

    When the cue moved far enough that clamping would pile every word onto one
    edge, the words are spread evenly across the cue instead. Collapsing them
    all to a single instant is technically inside the window but leaves the
    karaoke sweep with nothing to sweep, which is the same broken highlight in
    a different disguise."""
    if not words:
        return words
    out = []
    for w in words:
        ws = min(max(w[1], s), e)
        we = min(max(w[2], ws), e)
        out.append((w[0], ws, we) + tuple(w[3:]))
    if out[-1][2] - out[0][1] < 1e-6 < e - s:
        n = len(out)
        step = (e - s) / n
        out = [(w[0], s + i * step, s + (i + 1) * step) + tuple(w[3:])
               for i, w in enumerate(out)]
    return out


# ── Sync correction: cancelling the ASR's late word-start bias ──────────────
# Scribe, like every ASR, marks a word as starting where it gets LOUD — at the
# vowel — not where the speaker actually begins it. A leading fricative or
# plosive (ज़्यादातर, खाना, स्वाद) carries almost no energy, so it falls outside
# the word's own timestamp and the cue lands after the sound it transcribes.
#
# Measured against the waveform of a 40 s Hindi reel, on the 12 cues that begin
# out of clear silence (the only ones where the true onset is unambiguous):
# every single one was LATE, by +34 ms to +209 ms, median +70 ms — about 1.7
# frames at 24 fps, and up to 5. Not one was early. That is what "a few frames
# after" looks like, and it is not something frame rounding can explain.
#
# So: find the real onset in the waveform and move the cue back onto it. Only
# ever earlier, never later, and never past the previous cue — so the worst
# case for any cue is that it stays exactly where the ASR put it.
_ENV_HOP = 0.005            # envelope resolution: 5 ms, ~1/8 frame
_ENV_SR = 8000              # speech onsets need no more bandwidth than this
_ENV_THRESH = 0.04          # fraction of peak that counts as not-silence
_SNAP_MAX_PULL = 0.30       # never drag a start back further than this
_SNAP_DIP = 0.04            # quiet shorter than this is inside a word, not a gap
_SNAP_MIN_KEEP = 0.20       # never trim a preceding cue shorter than this
_DEFAULT_LEAD = 0.08        # fallback pull when no clean onset is available

_envelope_cache = {}


def _audio_envelope(path):
    """Peak-loudness envelope of ``path``, one value per _ENV_HOP, normalised
    to its own peak.

    Returns None when the audio cannot be decoded. ffmpeg is an OPTIONAL
    dependency of this script — it is not in requirements.txt and may simply be
    absent — so every caller has to stay useful without it."""
    if path in _envelope_cache:
        return _envelope_cache[path]

    env = None
    try:
        hop = int(_ENV_SR * _ENV_HOP)
        hop_bytes = hop * 2
        proc = subprocess.Popen(
            ["ffmpeg", "-v", "quiet", "-i", path, "-vn",
             "-ac", "1", "-ar", str(_ENV_SR), "-f", "s16le", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            # Without this a console window flashes up on every run: the
            # Resolve-side script side launches this script from Resolve with
            # no terminal attached.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        peaks = []
        raw = b""
        while True:
            chunk = proc.stdout.read(1 << 20)
            if not chunk:
                break
            raw += chunk
            full = len(raw) // hop_bytes
            if full:
                block = array.array("h")
                block.frombytes(raw[:full * hop_bytes])
                for k in range(full):
                    w = block[k * hop:(k + 1) * hop]
                    peaks.append(max(max(w), -min(w)))
                raw = raw[full * hop_bytes:]
        proc.stdout.close()
        proc.wait(timeout=10)
        top = max(peaks) if peaks else 0
        if top > 0:
            env = [p / top for p in peaks]
    except Exception as e:
        print("NOTE: onset sync unavailable for %s (%s); using a fixed lead."
              % (os.path.basename(path or ""), e))
        env = None

    _envelope_cache[path] = env
    return env


def _onset_before(env, t, max_pull):
    """Where the run of speech containing ``t`` actually begins, or None.

    Walks backwards from ``t`` through loud envelope hops, stepping over dips
    shorter than _SNAP_DIP (a plosive's own closure, the gap inside a
    conjunct), and stops at the first real gap. That gap is what proves the
    result is a word ONSET rather than a point somewhere inside a phrase.

    Returns None in the two cases where there is nothing to correct:
      * ``t`` is already in silence — the speech starts after the cue, so the
        cue is early, and this only ever moves cues earlier;
      * the walk used up ``max_pull`` still inside continuous speech — a cue
        starting mid-phrase, with no onset to snap to. Picking the nearest
        threshold crossing instead is worse than doing nothing: an early
        version did that, landed on intra-word dips a few ms back, and left
        the bias almost untouched."""
    hop = _ENV_HOP
    i = int(t / hop)
    if i <= 0 or i >= len(env) or env[i] <= _ENV_THRESH:
        return None

    limit = max(0, i - int(round(max_pull / hop)))
    dip = max(1, int(round(_SNAP_DIP / hop)))
    j, quiet, onset = i, 0, i
    while j > limit:
        j -= 1
        if env[j] > _ENV_THRESH:
            quiet = 0
            onset = j
        else:
            quiet += 1
            if quiet >= dip:
                return onset * hop
    return None


def apply_sync_correction(cues, audio_path, lead=_DEFAULT_LEAD,
                          max_pull=_SNAP_MAX_PULL):
    """Move cue starts back onto the speech they transcribe.

    Cues must be in the SOURCE file's own timebase (this reads that file's
    waveform), sorted, and non-overlapping — i.e. straight out of build_cues,
    before any timeline remapping.

    A cue that begins out of silence snaps to the measured onset. One that
    begins mid-phrase has no onset to snap to, so it gets ``lead`` instead —
    which is usually a no-op, because a mid-phrase cue butts against the cue
    before it and the clamp leaves it where it is. That is the right outcome:
    a cue running on from one already on screen has no late pop-in to fix.

    A cue's own end is never moved forward; the one before it can be trimmed
    back, and _sanitize_cues re-closes the gaps afterwards."""
    if not cues:
        return cues
    env = _audio_envelope(audio_path) if audio_path else None
    if not env and lead <= 0:
        return cues

    out = []
    prev_end = 0.0
    for cue in cues:
        i, s, e, text = cue[0], cue[1], cue[2], cue[3]
        words = list(cue[4]) if len(cue) > 4 else []

        ns = s - lead
        onset = _onset_before(env, s, max_pull) if env else None
        if onset is not None:
            ns = onset
            # ASR word ENDS overshoot just as starts do, so the previous cue
            # can still be running at the moment this word audibly begins —
            # which would pin this cue where it is. _onset_before only returns
            # a time it found real silence in front of, so that overlap is the
            # previous cue overstaying, not speech: hand the frames to the cue
            # that owns them. Skipped when it would leave the earlier cue too
            # short to read, since that trade is not worth making.
            if out and ns < prev_end and ns - out[-1][1] >= _SNAP_MIN_KEEP:
                po = out[-1]
                out[-1] = (po[0], po[1], ns, po[3],
                           _clamp_words(po[4], po[1], ns))
                prev_end = ns

        # Clamped three ways: never before the previous cue's end, never
        # before zero, and never so far that it swallows its own cue.
        ns = max(ns, prev_end, 0.0)
        if ns >= e:
            ns = s

        # The cue's first word has to travel with it, or the karaoke highlight
        # would still start at the old timestamp and the opening word would sit
        # unhighlighted for the frames we just gained.
        if words and words[0][1] > ns:
            wt, _ws, we, spk = words[0]
            words[0] = (wt, ns, max(we, ns), spk)

        out.append((i, ns, e, text, words))
        prev_end = e
    return out


# Where inside its frame a timestamp is written. Not 0.0: a value sitting
# exactly on a frame boundary can fall either side of it under float error, and
# not 0.5 either, because that is the tipping point for round-to-nearest. At
# 0.4 the timestamp reads as the same frame whether the importer truncates or
# rounds — and Resolve's SRT importer does not document which it does.
_FRAME_BIAS = 0.4


def _quantize_cues(cues, fps):
    """Snap every cue and word boundary onto the timeline's frame grid.

    Left alone, a cue time is an arbitrary float and the half-frame rounding is
    the importer's to make — and Resolve's SRT importer does not document
    which way it goes. Rounding here, once, settles it, and it is the last
    thing to touch a cue: everything upstream works in real seconds, where the
    audio actually lives.

    Starts floor onto the frame they fall in; ends round. A sound beginning
    part-way through a frame is already audible during that whole frame, so
    flooring puts the subtitle up with it, while rounding would hold it back a
    frame half the time — the exact one-frame lateness that survived the onset
    correction. Ends have no such argument, and rounding keeps durations
    honest."""
    if not fps or fps <= 0:
        return cues

    def q(t):
        return int(math.floor(t * fps + 0.5))

    framed = []
    for cue in cues:
        i, s, e, text = cue[0], cue[1], cue[2], cue[3]
        words = cue[4] if len(cue) > 4 else []
        sf, ef = int(math.floor(s * fps)), q(e)
        if ef <= sf:
            ef = sf + 1
        if framed:
            psf, pef = framed[-1][1], framed[-1][2]
            # Rounding can close the 1 ms gaps _sanitize_cues leaves, which is
            # wanted (the clips end up flush), but it can also push two cues
            # into a real overlap. Give the frame to the later cue and trim the
            # earlier one, unless that would erase it.
            if sf < pef:
                if sf > psf:
                    framed[-1] = (framed[-1][0], psf, sf,
                                  framed[-1][3], framed[-1][4])
                else:
                    sf = pef
                    if ef <= sf:
                        ef = sf + 1
        qwords = []
        for wt, ws, we, spk in words:
            wsf = min(max(int(math.floor(ws * fps)), sf), ef)
            wef = min(max(q(we), wsf), ef)
            qwords.append((wt, wsf, wef, spk))
        framed.append((i, sf, ef, text, qwords))

    bias = _FRAME_BIAS / fps
    return [(i, sf / fps + bias, ef / fps + bias, text,
             [(wt, wsf / fps + bias, wef / fps + bias, spk)
              for wt, wsf, wef, spk in words])
            for i, sf, ef, text, words in framed]


def _sanitize_cues(cues, min_dur=0.04, read_dur=0.0,
                   close_gap=_GAP_CLOSE_MAX):
    """Make any cue list a valid SRT: sorted, non-overlapping, positive
    durations, 1-based contiguous numbering.

    With multiple clips (retakes) on one track, cues from different clips can
    collide at the cut points. Overlaps are resolved by truncating the earlier
    cue at the later one's start when possible; when that would erase the
    earlier cue, the later cue is nudged forward instead — text is never
    dropped, and every cue keeps at least ``min_dur`` seconds on screen.

    Whenever a cue's own start/end moves, its per-word timings move with it
    (_clamp_words). Those words are what ends up in the .cap sidecar, and the
    macro turns them into karaoke keyframes relative to the cue start — so
    a word left behind at its pre-nudge timestamp became a NEGATIVE keyframe
    frame, and the highlight for that cue never played."""
    cleaned = []
    for cue in sorted(cues, key=lambda c: (c[1], c[2])):
        s, e, text, words = cue[1], cue[2], cue[3], (cue[4] if len(cue) > 4 else [])
        if not text.strip():
            continue
        if e <= s:
            e = s + min_dur
        if cleaned:
            ps, pe = cleaned[-1][0], cleaned[-1][1]
            if s < pe:
                if s - ps >= min_dur:
                    # truncate prev, and pull its words back inside the new end
                    cleaned[-1] = (ps, s, cleaned[-1][2],
                                   _clamp_words(cleaned[-1][3], ps, s))
                else:
                    s = pe                                   # nudge this cue
                    if e < s + min_dur:
                        e = s + min_dur
        cleaned.append((s, e, text, _clamp_words(words, s, e)))

    # Readability pass (AutoSubs-style): a cue shorter than ``read_dur`` is
    # extended into the following silence so it stays on screen long enough
    # to read, stopping 1 ms before the next cue starts.
    if read_dur > min_dur:
        for i, (s, e, text, words) in enumerate(cleaned):
            if e - s < read_dur:
                limit = cleaned[i + 1][0] - 0.001 if i + 1 < len(cleaned) else s + read_dur
                # Only the end grows here, so the words are still inside it —
                # no re-clamp needed, and none wanted: a word must not be
                # stretched into silence just because the cue was.
                cleaned[i] = (s, max(e, min(s + read_dur, limit)), text, words)

    # Gap-closing pass: a short silence between two cues is absorbed by the
    # earlier one, leaving 1 ms so the SRT stays non-overlapping (sub-frame, so
    # Resolve rounds the two clips flush against each other). Only the end
    # moves, so the words stay inside the cue and are deliberately NOT stretched
    # with it — the karaoke highlight must still follow the spoken audio.
    if close_gap > 0:
        for i in range(len(cleaned) - 1):
            s, e, text, words = cleaned[i]
            nxt = cleaned[i + 1][0]
            if 0.0 < nxt - e <= close_gap:
                cleaned[i] = (s, max(e, nxt - 0.001), text, words)

    return [(i + 1, s, e, t, w) for i, (s, e, t, w) in enumerate(cleaned)]


def build_and_remap_cues(words_by_source, max_chars, max_lines, max_secs, ranges,
                         include_punct="1", cps=0.0, min_dur=0.0, max_words=0,
                         lang=None, audio_path=None):
    """Assign words to their clip by (source file, source-start time), build cues
    within each clip independently, then remap timestamps to the timeline.

    ``words_by_source`` maps source file path → list of words (the transcription
    result for that file). For legacy single-source callers, pass
    ``{None: words}`` and ranges without a ``src_path``."""
    if not ranges:
        # No ranges → fall back to the first (and typically only) word list.
        # No fps either, so the frame grid is unknown and quantising is skipped;
        # the onset correction still applies, and it is the larger of the two.
        flat = next(iter(words_by_source.values()), [])
        cues = build_cues(flat, max_chars, max_lines, max_secs, include_punct,
                          cps, max_words, lang)
        return _sanitize_cues(apply_sync_correction(cues, audio_path),
                              read_dur=min_dur)

    # For each range, pull words from its source file's word list that fall in
    # the range's source-time window, by containment only. A word may belong
    # to more than one range: when the editor uses the SAME source region
    # twice on the timeline (duplicated take), both clips must get subtitles.
    # Timeline-side collisions are resolved later by clamping each clip's cues
    # to its own timeline window plus a global overlap pass.
    range_words = {i: [] for i in range(len(ranges))}
    for i, r in enumerate(ranges):
        src = r.get("src_path")
        if src in words_by_source:
            candidates = words_by_source[src]
        else:
            # Legacy / unknown source: fall back to the single bucket if there
            # is exactly one, otherwise skip (no transcription for this clip).
            candidates = next(iter(words_by_source.values())) if len(words_by_source) == 1 else []
        for w in candidates:
            ws = float(getattr(w, "start", 0) or 0)
            if r["src_start_s"] <= ws < r["src_end_s"]:
                range_words[i].append(w)

    all_cues = []
    for i, r in enumerate(ranges):
        clip_words = range_words[i]
        if not clip_words:
            continue
        cues = build_cues(clip_words, max_chars, max_lines, max_secs,
                          include_punct, cps, max_words, lang)
        # Onset snapping has to happen HERE, before the shift: these cues are
        # still in the source file's own timebase, which is the one its
        # waveform is in. A clip's own window also bounds the pull, so a cue
        # cannot be dragged back past the cut that starts its clip.
        cues = apply_sync_correction(cues, r.get("src_path") or audio_path)
        shift = r["tl_start_s"] - r["src_start_s"] - r["anchor_s"]
        # The clip occupies this window on the timeline. Transcription word
        # end-times often run past the spoken word into silence; when the
        # editor cut the clip right there (retake trims), an unclamped cue
        # would spill into the NEXT clip and overlap its first cue. Clamp
        # every cue to its own clip's window so cuts stay clean.
        win_start = r["tl_start_s"] - r["anchor_s"]
        win_end   = win_start + (r["src_end_s"] - r["src_start_s"])
        for _, s, e, text, words in cues:
            ns = max(0.0, win_start, s + shift)
            ne = min(e + shift, win_end)
            if ne > ns:
                # Shift each word's timing onto the timeline too, so animated
                # captions highlight at the right moment; clamp to the cue.
                shifted = [(wt, min(max(ws + shift, ns), ne),
                                min(max(we + shift, ns), ne), spk)
                           for wt, ws, we, spk in words]
                all_cues.append((0, ns, ne, text, shifted))

    # Cues were built one clip at a time, so no clip ever saw its neighbour's
    # last words — the one case _reattach_clitics exists for that build_cues
    # cannot cover. Run it once over the assembled, timeline-ordered list so a
    # cue at a cut does not open with है / ছিল / ஆகும் / ہے either. Sorting
    # first because the pass only ever looks at the cue immediately before.
    merged = sorted(all_cues, key=lambda c: (c[1], c[2]))
    merged = _reattach_clitics(merged, max_chars, max_lines, max_words,
                               max_secs=max_secs, lang=lang)
    return _quantize_cues(_sanitize_cues(merged, read_dur=min_dur),
                          ranges[0]["fps"])


_MIME = {
    ".aac": "audio/aac", ".aiff": "audio/aiff", ".aif": "audio/aiff",
    ".alac": "audio/alac", ".flac": "audio/flac", ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg", ".mpeg": "audio/mpeg", ".mpga": "audio/mpeg",
    ".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/opus",
    ".wav": "audio/wav", ".wma": "audio/x-ms-wma", ".caf": "audio/x-caf",
    # Video containers: the timeline's clips are usually camera/NLE masters, so
    # these are the extensions actually seen in clip_ranges.txt. Left out, they
    # fell through to application/octet-stream and Scribe rejected the upload.
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
    ".mkv": "video/x-matroska", ".webm": "video/webm", ".avi": "video/x-msvideo",
    ".mxf": "application/mxf", ".mts": "video/mp2t", ".m2ts": "video/mp2t",
    ".wmv": "video/x-ms-wmv", ".mpg": "video/mpeg", ".r3d": "video/x-red-r3d",
}


# ── Transcript cache ─────────────────────────────────────────────────────────
# The ElevenLabs Scribe call is the only slow, paid step in the pipeline. Its
# output — the raw word list with per-word timing and speaker ids — depends
# ONLY on (audio content, model, language, diarize flag), never on how we later
# split the words into cues. So we cache that raw word list and skip the API
# whenever the same audio is transcribed again with the same options. This is
# what makes re-splitting (different max_chars/cps/lines) instant and free:
# only the local cue-building runs, never the network.
#
# Fingerprint is sampled, not a full-file hash — media files are often GBs and
# a full read would defeat the point. We hash file size plus the first and last
# 1 MiB; that changes whenever the audio does but stays cheap on huge files.
_CACHE_VER = 1
_CACHE_SAMPLE = 1 << 20  # 1 MiB from each end


class _RawW:
    """Duck-typed raw word restored from cache: same attributes the live
    ElevenLabs word objects expose, so _normalize_words treats them alike."""
    __slots__ = ("text", "start", "end", "speaker_id")

    def __init__(self, text, start, end, speaker_id):
        self.text = text
        self.start = start
        self.end = end
        self.speaker_id = speaker_id


def _cache_dir():
    d = os.path.join(PIPELINE_DIR, ".cache")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _file_fingerprint(path):
    """Cheap content fingerprint: size + first/last 1 MiB. Returns "" on error
    so the caller falls back to a live transcription rather than a bad hit."""
    import hashlib
    try:
        size = os.path.getsize(path)
        h = hashlib.sha1()
        h.update(str(size).encode())
        with open(path, "rb") as f:
            h.update(f.read(_CACHE_SAMPLE))
            if size > _CACHE_SAMPLE:
                f.seek(max(0, size - _CACHE_SAMPLE))
                h.update(f.read(_CACHE_SAMPLE))
        return h.hexdigest()
    except Exception:
        return ""


def _cache_key(path, model_id, language, diarize):
    fp = _file_fingerprint(path)
    if not fp:
        return None
    import hashlib
    raw = "%d|%s|%s|%s|%d" % (_CACHE_VER, fp, model_id, language, 1 if diarize else 0)
    return hashlib.sha1(raw.encode()).hexdigest()


def _cache_load(key):
    """Return the cached raw word list for ``key`` (as _RawW objects), or None."""
    if not key:
        return None
    path = os.path.join(_cache_dir(), key + ".json")
    if not os.path.exists(path):
        return None
    try:
        import json
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [_RawW(w.get("text", ""), float(w.get("start", 0) or 0),
                      float(w.get("end", 0) or 0), w.get("speaker_id"))
                for w in data.get("words", [])]
    except Exception:
        return None


def _cache_store(key, words):
    """Persist the raw word list for ``key``. Best-effort; never raises."""
    if not key:
        return
    try:
        import json
        payload = {"ver": _CACHE_VER, "words": [
            {"text": getattr(w, "text", "") or "",
             "start": float(getattr(w, "start", 0) or 0),
             "end": float(getattr(w, "end", 0) or 0),
             "speaker_id": getattr(w, "speaker_id", None)}
            for w in words]}
        tmp = os.path.join(_cache_dir(), key + ".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(_cache_dir(), key + ".json"))
    except Exception:
        pass


class _Word:
    """Duck-type word passed to build_cues: exposes .text/.start/.end/.speaker."""
    __slots__ = ("text", "start", "end", "speaker")

    def __init__(self, text, start, end, speaker):
        self.text = text
        self.start = start
        self.end = end
        self.speaker = speaker


def normalize_words(raw_words, script, diarize):
    """Turn raw transcript words (from API or cache) into _Word objects,
    applying the Latin→target-script safety net and carrying the diarization
    speaker only when diarize is on. Shared by the live-transcribe path (main)
    and the re-split-from-cache path (resplit).

    ``script`` is 'dev', 'beng', None (leave Latin words as they are) or the
    'auto' sentinel, which infers the target from the transcript itself."""
    if script == "auto":
        script = _dominant_script(raw_words)
    out = []
    for w in raw_words:
        text = getattr(w, "text", "") or ""
        if script:
            text = transliterate(text, script)
        out.append(_Word(text,
                         float(getattr(w, "start", 0) or 0),
                         float(getattr(w, "end", 0) or 0),
                         getattr(w, "speaker_id", None) if diarize else None))
    return out


def _transcribe_upload(path, lang_code, diarize, client):
    """One Scribe call for the audio file at ``path``, with no caching around
    it. ``path`` may be a whole source file or a cut-out window of one, so the
    word times come back relative to whatever was uploaded — the caller owns
    putting them into the source's timebase."""
    ext = os.path.splitext(path)[1].lower()
    mime = _MIME.get(ext, "application/octet-stream")
    with open(path, "rb") as fh:
        # language_code pins the transcript's script: Hindi ("hin") makes
        # ElevenLabs write everything in Devanagari, including
        # code-switched English (e.g. "sky" → "स्काई"). With the auto
        # sentinel the parameter is omitted so Scribe detects the language
        # itself — any language, but mixed Latin/Devanagari is then possible.
        kwargs = {}
        if diarize:
            kwargs["diarize"] = True
        if not is_auto_lang(lang_code):
            kwargs["language_code"] = lang_code
        result = client.speech_to_text.convert(
            file=(os.path.basename(path), fh, mime),
            model_id="scribe_v2",
            timestamps_granularity="word",
            tag_audio_events=False,
            **kwargs
        )
    if not result:
        return []
    return list(getattr(result, "words", None) or [])


def fetch_words(path, lang_code, diarize, client):
    """Return the raw word list for ``path``: a transcript-cache hit skips the
    paid Scribe call entirely, otherwise call the API and store the result
    for next time. Shared by main()'s generate path and the SRT-sync path."""
    key = _cache_key(path, "scribe_v2", lang_code, diarize)
    cached = _cache_load(key)
    if cached is not None:
        print("Cache hit: %s (%d words, no API call)"
              % (os.path.basename(path), len(cached)))
        return cached

    print("Transcribing: " + os.path.basename(path))
    words = _transcribe_upload(path, lang_code, diarize, client)
    if not words:
        print("ERROR: ElevenLabs returned no word data for " + path)
        return []
    # Store the raw word list so future runs / re-splits of this same audio
    # are instant and free. Best-effort — a cache write failure never
    # affects this run's output.
    _cache_store(key, words)
    return words


# ── Uploading only the part of a source the timeline actually uses ──────────
# A trimmed clip covers a small part of its source file, but Scribe bills by
# the audio duration it receives — so uploading the whole file and then
# discarding most of the words (build_and_remap_cues keeps only those inside
# each clip's own source window) pays for material that can never reach the
# SRT. When ffmpeg is available, cut the used region out first and send that.
#
# Everything downstream keeps working in the SOURCE file's timebase: a slice's
# words come back relative to the slice, and are shifted by the window start
# before any caller sees them. The clip-range filter, the onset correction
# (which reads the full source waveform) and the timeline remap are unchanged.
_SLICE_PAD = 0.5        # context either side, so a cut never lands mid-word
_SLICE_MERGE_GAP = 2.0  # windows closer than this cost less merged than apart
_SLICE_MIN_WAV = 1024   # a wav below this is a bare header, not audio


def _source_windows(ranges, src_path, diarize=False):
    """Merged source-time windows worth transcribing for ``src_path``.

    Every clip contributes its own [src_start, src_end); overlapping and
    nearly-adjacent ones merge. Windows are padded and snapped out to whole
    seconds, so nudging a trim by a few frames reuses the cached transcript
    instead of paying for a new one. ``src_path`` of None means "every
    range", which is the legacy 5-field layout whose rows carry no path.

    With diarize on, separate windows would mean separate API calls, and
    Scribe numbers speakers per call — speaker_0 in one window need not be
    the same person as speaker_0 in the next. So they collapse to the single
    span covering them all: one call, consistent ids, and still never more
    audio than the whole file.
    """
    spans = []
    for r in ranges:
        if src_path is not None and r.get("src_path") != src_path:
            continue
        s, e = r.get("src_start_s"), r.get("src_end_s")
        if s is None or e is None or e <= s:
            continue
        spans.append((max(0.0, float(math.floor(s - _SLICE_PAD))),
                      float(math.ceil(e + _SLICE_PAD))))
    if not spans:
        return []
    spans.sort()
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1] + _SLICE_MERGE_GAP:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    if diarize and len(merged) > 1:
        merged = [[merged[0][0], merged[-1][1]]]
    return [(float(s), float(e)) for s, e in merged]


def _slice_cache_key(path, model_id, language, diarize, start, end):
    """Cache key for one transcribed window of ``path``. Deliberately distinct
    from the whole-file key: a sliced transcript covers only its window, and
    must never be served as though it were the entire file."""
    fp = _file_fingerprint(path)
    if not fp:
        return None
    import hashlib
    raw = "%d|%s|%s|%s|%d|%.3f|%.3f" % (_CACHE_VER, fp, model_id, language,
                                        1 if diarize else 0, start, end)
    return hashlib.sha1(raw.encode()).hexdigest()


def _cached_words_for_windows(path, windows, model_id, language, diarize):
    """Raw words for ``path`` in source timebase, from cache only — no API.

    The whole-file entry is tried first because it covers every window, so an
    earlier untrimmed run makes a trimmed re-split free. Returns None when
    anything needed is missing, which is resplit()'s signal to fall back to a
    real transcription."""
    full = _cache_load(_cache_key(path, model_id, language, diarize))
    if full is not None:
        return full
    if not windows:
        return None
    out = []
    for ws, we in windows:
        got = _cache_load(_slice_cache_key(path, model_id, language,
                                           diarize, ws, we))
        if got is None:
            return None
        out.extend(got)
    out.sort(key=lambda w: float(getattr(w, "start", 0) or 0))
    return out


def _slice_audio(path, start, end, dest):
    """Cut [start, end) of ``path`` into ``dest`` as 16 kHz mono PCM wav.

    Mono 16 kHz is what speech recognition wants and it keeps the upload
    small, which is the whole point of slicing. Returns False on any failure:
    ffmpeg is an OPTIONAL dependency of this script, so every caller has to
    stay useful without it."""
    dur = end - start
    if dur <= 0:
        return False
    try:
        subprocess.run(
            ["ffmpeg", "-v", "quiet", "-nostdin", "-y",
             # -accurate_seek with -ss BEFORE -i: seek fast, then decode and
             # discard to the exact sample. A keyframe-rounded seek would
             # shift every word in the window — a real sync error, not a
             # rounding detail.
             "-accurate_seek", "-ss", "%.3f" % start,
             "-i", path, "-t", "%.3f" % dur,
             "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
             "-f", "wav", dest],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=600,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return os.path.exists(dest) and os.path.getsize(dest) > _SLICE_MIN_WAV
    except Exception as e:
        print("NOTE: could not cut audio from %s (%s)."
              % (os.path.basename(path or ""), e))
        return False


def fetch_words_ranged(path, windows, lang_code, diarize, client):
    """fetch_words for a source the timeline only partly uses: upload just
    ``windows`` rather than the whole file.

    Words are returned in the SOURCE file's timebase, exactly as the
    whole-file path returns them, so callers and everything downstream cannot
    tell the two apart. Falls back to the whole file whenever slicing is
    unavailable, which leaves today's behaviour intact without ffmpeg."""
    if not windows:
        return fetch_words(path, lang_code, diarize, client)

    # An earlier untrimmed run already paid for every window.
    full = _cache_load(_cache_key(path, "scribe_v2", lang_code, diarize))
    if full is not None:
        print("Cache hit: %s (%d words, no API call)"
              % (os.path.basename(path), len(full)))
        return full

    import tempfile
    name = os.path.basename(path)
    total = sum(e - s for s, e in windows)
    print("Trimmed upload: %d window(s) of %s, %.1fs of audio"
          % (len(windows), name, total))

    out = []
    for ws, we in windows:
        key = _slice_cache_key(path, "scribe_v2", lang_code, diarize, ws, we)
        cached = _cache_load(key)
        if cached is not None:
            print("Cache hit: %s [%.1fs-%.1fs] (%d words, no API call)"
                  % (name, ws, we, len(cached)))
            out.extend(cached)
            continue

        fd, tmp = tempfile.mkstemp(suffix=".wav", dir=_cache_dir())
        os.close(fd)
        try:
            if not _slice_audio(path, ws, we, tmp):
                # Without ffmpeg there is nothing to slice with, and one
                # whole-file call subsumes every window — so stop slicing
                # this source entirely rather than failing window by window.
                print("NOTE: cutting %s failed; transcribing the whole file."
                      % name)
                return fetch_words(path, lang_code, diarize, client)
            print("Transcribing: %s [%.1fs-%.1fs]" % (name, ws, we))
            words = _transcribe_upload(tmp, lang_code, diarize, client)
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass

        if not words:
            # A trimmed window can legitimately be silent, so this is a note
            # rather than an error. Not cached: an empty list here is
            # indistinguishable from a failed call, and caching a failure
            # would make it permanent.
            print("NOTE: no words in %s [%.1fs-%.1fs]." % (name, ws, we))
            continue

        # Back into the source file's timebase before anyone else sees them.
        shifted = [_RawW(getattr(w, "text", "") or "",
                         float(getattr(w, "start", 0) or 0) + ws,
                         float(getattr(w, "end", 0) or 0) + ws,
                         getattr(w, "speaker_id", None))
                   for w in words]
        _cache_store(key, shifted)
        out.extend(shifted)

    if not out:
        print("ERROR: ElevenLabs returned no word data for " + path)
        return []
    out.sort(key=lambda w: float(getattr(w, "start", 0) or 0))
    return out


# ── SRT-sync: re-time an existing SRT against the audio ─────────────────────
# Scenario: an SRT exists with correct text but wrong/drifted timestamps
# (hand-typed, exported elsewhere, or from an earlier bad run). We re-transcribe
# the audio for real word timings, then align the SRT's own words to those
# timings by text match — text is never altered, only start/end times.
_SRT_TIME_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})")


def _parse_srt_ts(ts):
    h, m, rest = ts.strip().replace(".", ",").split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path):
    """Parse an .srt file into [(start_s, end_s, text), ...] in file order.

    The timestamps are returned for reference only — sync_srt_timing()
    discards them, since fixing bad timing is the whole point. Blocks with
    empty text are skipped (drops stray blank cues, e.g. this pipeline's own
    zero-length header entry written by to_srt())."""
    with open(path, encoding="utf-8-sig") as f:
        content = f.read()
    cues = []
    for block in re.split(r"\r?\n\r?\n+", content.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if not lines:
            continue
        li = 1 if lines[0].strip().isdigit() else 0
        if li >= len(lines):
            continue
        m = _SRT_TIME_RE.search(lines[li])
        if not m:
            continue
        text = "\n".join(lines[li + 1:]).strip()
        if text:
            cues.append((_parse_srt_ts(m.group(1)), _parse_srt_ts(m.group(2)), text))
    return cues


def _norm_tok(token):
    """Normalize a word for cross-transcript matching: NFC, lowercase,
    punctuation stripped (_PUNCT_STRIP, so the Devanagari danda/quotes etc.
    are handled too)."""
    return unicodedata.normalize("NFC", token.strip(_PUNCT_STRIP).lower())


# ── Reference script: your spellings, and your punctuation ──────────────────
# Scribe writes what it hears, so proper nouns, borrowed words and anything
# carrying a nukta come out however the model guessed — सदगुरु for सद्गुरु,
# हफ्तों for हफ़्तों. The script the VO was read from already has all of that
# right, so when one is supplied it becomes the authority on spelling.
#
# It fixes the chunking too, and through the machinery that already exists
# rather than a second mechanism: build_cues splits on _STRONG_END /
# _WEAK_END read off each word's raw text, and ASR punctuation is a guess
# while a script's is authored. Adopting the reference token *with* its
# punctuation hands the splitter real sentence and clause boundaries.
#
# Hard rules, because a VO never matches its script exactly — takes get
# re-read, lines get ad-libbed, whole paragraphs get cut:
#   • the word COUNT never changes, and neither does the order or any
#     timestamp. Only the text of a word already there can change.
#   • a word is only re-spelled when it is recognisably the same word. Below
#     _REF_MIN_RATIO the two are treated as different words and the spoken one
#     stands — that is what keeps an ad lib from being rewritten into whatever
#     the script happened to say at that point.
_REF_MIN_RATIO = 0.62

# Word counts either side of a mismatch must agree before anything is
# re-spelled. A block where the speaker said three words and the script has
# five is a genuine deviation, not a spelling difference.


def _docx_text(path):
    """Visible text of a .docx.

    A .docx is a zip whose word/document.xml holds the body: `<w:t>` elements
    are the text runs and `</w:p>` ends a paragraph. Pulled out with zipfile
    and a regex rather than a library, because python-docx is not a dependency
    of this project and a script file is not worth making it one."""
    import zipfile
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    # Paragraph and line breaks first, so the last word of one line and the
    # first of the next do not fuse into a single token.
    xml = re.sub(r"</w:p\s*>", "\n", xml)
    xml = re.sub(r"<w:(?:br|cr)\b[^>]*/?>", "\n", xml)
    xml = re.sub(r"<w:tab\b[^>]*/?>", " ", xml)
    parts = []
    for m in re.finditer(r"<w:t(?:\s[^>]*)?>(.*?)</w:t\s*>|(\n)", xml, re.S):
        parts.append(m.group(1) if m.group(1) is not None else "\n")
    return html.unescape("".join(parts))


def read_reference_script(path):
    """The words of a reference script, in order, with their punctuation.

    Accepts .docx, .srt (an existing subtitle file makes a fine script) and
    anything else as plain text. Returns [] when the file cannot be read at
    all — a bad script must degrade to "no script", never break the run."""
    if not path or not os.path.exists(path):
        return []
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".docx":
            text = _docx_text(path)
        elif ext == ".srt":
            text = "\n".join(c[2] for c in parse_srt(path))
        else:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                text = f.read()
    except Exception as e:
        print("WARNING: could not read the script file (%s): %s"
              % (os.path.basename(path), e))
        return []
    return unicodedata.normalize("NFC", text).split()


def _apply_ref_script(words_by_source, ref_script):
    """Run the reference script over every source's words and report on it.

    The match rate is the number worth printing. A script for the wrong cut —
    or, as happens with these reels, the English source script against a Hindi
    VO — matches almost nothing and corrects almost nothing, and saying so is
    the difference between "the script did nothing" and "the script silently
    did nothing"."""
    ref_tokens = read_reference_script(ref_script)
    if not ref_tokens:
        return words_by_source
    out = {}
    total = corrected = matched = 0
    for sp, ws in words_by_source.items():
        ws, c, m = apply_reference_spelling(ws, ref_tokens)
        out[sp] = ws
        total += sum(1 for w in ws if w.text.strip())
        corrected += c
        matched += m
    pct = (100.0 * matched / total) if total else 0.0
    print("Script: %s — matched %d of %d words (%.0f%%), corrected %d spelling(s)."
          % (os.path.basename(ref_script), matched, total, pct, corrected))
    if pct < 40.0:
        print("WARNING: the script barely matches what was said (%.0f%%). It may "
              "be for a different cut, or in a different language than the "
              "audio — nothing was changed where it did not match." % pct)
    return out


def apply_reference_spelling(words, ref_tokens, min_ratio=_REF_MIN_RATIO):
    """Adopt the script's spelling and punctuation for the words it matches.

    ``words`` is the _Word list from the transcription; ``ref_tokens`` the
    output of read_reference_script. Returns (words, corrected, matched) —
    a NEW list of the same length in the same order, the number of words whose
    text changed, and the number the script accounted for at all.

    The matched count is the useful diagnostic: a script for the wrong video
    matches almost nothing and corrects almost nothing, which is visible in
    the log rather than silently reshaping the subtitles."""
    if not words or not ref_tokens:
        return words, 0, 0

    # Scribe emits a spacing entry between every pair of words — half of a
    # 283-entry transcript is " ". They normalise to nothing and can never
    # match, so left in they shred the diff: a single changed word turns into
    # a delete/replace/delete run whose counts no longer line up, and the
    # equal-count guard below then (correctly, but uselessly) declines to touch
    # it. Align the real words only, and map back through ``real``.
    # _norm_tok strips punctuation but not whitespace, so it maps " " to " " —
    # truthy, which let every spacing entry back through the filter and put the
    # diff right back where it started.
    def norm(t):
        return _norm_tok(t).strip()

    real = [i for i, w in enumerate(words) if norm(w.text)]
    asr_norm = [norm(words[i].text) for i in real]
    ref_keep = [t for t in ref_tokens if norm(t)]
    ref_norm = [norm(t) for t in ref_keep]
    sm = difflib.SequenceMatcher(None, asr_norm, ref_norm, autojunk=False)

    out = list(words)
    corrected = matched = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            # Same word already. Still worth taking the reference token: it
            # carries the punctuation the splitter needs, and the ASR's is a
            # guess. Skip a reference token that is bare punctuation.
            for k, j in zip(range(i1, i2), range(j1, j2)):
                i = real[k]
                matched += 1
                new = ref_keep[j]
                if new != words[i].text:
                    out[i] = _Word(new, words[i].start, words[i].end,
                                   words[i].speaker)
                    corrected += 1
        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            # Equal counts on both sides: word-for-word differences, which is
            # what a spelling variant looks like. Unequal counts mean the
            # speaker genuinely departed from the script, and nothing is
            # touched there.
            for k, j in zip(range(i1, i2), range(j1, j2)):
                i = real[k]
                if difflib.SequenceMatcher(
                        None, asr_norm[k], ref_norm[j]).ratio() >= min_ratio:
                    matched += 1
                    if ref_keep[j] != words[i].text:
                        out[i] = _Word(ref_keep[j], words[i].start,
                                       words[i].end, words[i].speaker)
                        corrected += 1
    return out, corrected, matched


# Fraction of the SRT's words that must match the fresh transcription for the
# alignment to be believable. Interpolation covers the gaps between matched
# anchors, so this does not need to be high — but below it there are no anchors
# worth interpolating between, and what comes out is not a re-timing, it is a
# pile of cues at t=0. 0.25 passes a heavily-edited or partly-paraphrased SRT
# and fails the wrong-file / wrong-language case.
_ALIGN_MIN_MATCH = 0.25


class AlignmentFailed(Exception):
    """The SRT's text does not correspond to this audio. Message is written to
    be shown to the user as-is."""


def _align_srt_to_words(srt_cues, asr_words, audio_path=None):
    """Re-time ``srt_cues`` (list of (old_start, old_end, text) from an
    existing SRT — the old times are ignored) to match ``asr_words`` (real
    ASR word timings for the same audio), keeping every cue's text unchanged.

    Matches via difflib over normalized tokens so minor transcription
    differences (typos, transliteration drift) don't break alignment; any
    unmatched run of words is interpolated between its nearest matched
    neighbours (or clamped to one neighbour at the very start/end). Returns
    cues already run through _sanitize_cues() — non-overlapping, min-duration,
    correctly numbered.

    Raises AlignmentFailed when too little of the SRT matched to trust the
    result. Without that check this function always returned one cue per input
    cue, so main_sync's "could not align any cues" branch was unreachable and a
    mismatched SRT — wrong file, wrong language, wrong take — was written out as
    a success with every cue stacked at the start of the timeline."""
    srt_tokens = []  # (cue_index, word_text)
    for ci, (_s, _e, text) in enumerate(srt_cues):
        for w in text.split():
            srt_tokens.append((ci, w))

    asr_tokens = [(w.text, float(w.start), float(w.end)) for w in asr_words
                  if getattr(w, "text", "").strip()]

    norm_srt = [_norm_tok(t[1]) for t in srt_tokens]
    norm_asr = [_norm_tok(t[0]) for t in asr_tokens]

    times = [None] * len(srt_tokens)
    sm = difflib.SequenceMatcher(None, norm_srt, norm_asr, autojunk=False)
    matched = 0
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            aj = block.b + k
            times[block.a + k] = (asr_tokens[aj][1], asr_tokens[aj][2])
            matched += 1

    if not srt_tokens or not asr_tokens:
        raise AlignmentFailed(
            "Nothing to align: the SRT has no text, or the transcription "
            "returned no words.")
    ratio = matched / float(len(srt_tokens))
    if ratio < _ALIGN_MIN_MATCH:
        raise AlignmentFailed(
            "Only %d%% of the subtitle text could be found in this audio, so "
            "the timings would be guesses rather than a re-sync.\n\n"
            "Check that the SRT belongs to the audio track you picked, and "
            "that the language matches — a Hindi SRT against a Tamil take "
            "looks exactly like this." % int(round(ratio * 100)))

    n = len(times)
    i = 0
    while i < n:
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < n and times[j] is None:
            j += 1
        prev_t = times[i - 1][1] if i > 0 else None
        next_t = times[j][0] if j < n else None
        if prev_t is None and next_t is None:
            for k in range(i, j):
                times[k] = (0.0, 0.0)
        elif prev_t is None:
            for k in range(i, j):
                times[k] = (next_t, next_t)
        elif next_t is None:
            for k in range(i, j):
                times[k] = (prev_t, prev_t)
        else:
            span, count = next_t - prev_t, j - i
            for k in range(i, j):
                times[k] = (prev_t + span * (k - i) / count,
                            prev_t + span * (k - i + 1) / count)
        i = j

    cue_times = {}
    for (ci, _w), (ws, we) in zip(srt_tokens, times):
        if ci not in cue_times:
            cue_times[ci] = [ws, we]
        else:
            cue_times[ci][0] = min(cue_times[ci][0], ws)
            cue_times[ci][1] = max(cue_times[ci][1], we)

    cues = []
    for ci, (_s, _e, text) in enumerate(srt_cues):
        s, e = cue_times.get(ci, (0.0, 0.0))
        if e <= s:
            e = s + 0.04
        cues.append((0, s, e, text, []))

    # These starts came from the same ASR word timings as a fresh transcription
    # does, so they carry the same late bias and get the same correction.
    return _sanitize_cues(apply_sync_correction(cues, audio_path), read_dur=0.0)


def sync_srt_timing(srt_path, audio_path, lang_code, diarize=False, client=None):
    """Re-time an existing SRT (right text, wrong timestamps) against the
    audio using ElevenLabs word-level ASR + text alignment. Text is never
    changed — only start/end times."""
    if client is None:
        from elevenlabs import ElevenLabs
        client = ElevenLabs(api_key=os.environ.get("ELEVENLABS_API_KEY", "").strip())

    resolved_lang = (os.environ.get("ELEVENLABS_LANGUAGE", "").strip()
                     or lang_code or HINDI_LANG_CODE)
    script = script_for_lang(resolved_lang)

    srt_cues = parse_srt(srt_path)
    if not srt_cues:
        raise AlignmentFailed(
            "No subtitle cues could be read from that file. Check that it is a "
            "valid .srt (numbered blocks with 00:00:00,000 --> timestamps).")

    raw_words = fetch_words(audio_path, resolved_lang, diarize, client)
    asr_words = normalize_words(raw_words, script, diarize)

    return _align_srt_to_words(srt_cues, asr_words, audio_path)


def resplit(audio_path, srt_output, ranges_path, *, max_chars, max_lines,
            max_secs, include_punct="1", lang_code=HINDI_LANG_CODE,
            diarize=False, cps=20.0, min_dur=0.4, max_words=0,
            ref_script=None, write=True):
    """Rebuild cues from CACHED transcripts only — never calls the API.

    Returns (cues, fps) when every needed source is already cached, or None on
    any cache miss (the caller should then run a full transcription). This is
    the engine behind instant, free re-splitting: change max_chars / cps /
    lines / speakers and the transcript is reused, only the local cue-building
    re-runs. When ``write`` is true it also writes the SRT and .cap sidecar,
    matching main()'s output exactly."""
    resolved_lang = (os.environ.get("ELEVENLABS_LANGUAGE", "").strip()
                     or lang_code or HINDI_LANG_CODE)
    script = script_for_lang(resolved_lang)

    ranges = read_clip_ranges(ranges_path)
    unique_sources = []
    seen = set()
    for r in ranges:
        sp = r.get("src_path")
        if sp and sp not in seen:
            seen.add(sp)
            unique_sources.append(sp)

    words_by_source = {}
    sources = unique_sources if unique_sources else [audio_path]
    legacy_single = not unique_sources
    for sp in sources:
        # Windows must be derived exactly as the transcribing path derives
        # them, or a sliced run would never be re-splittable for free.
        windows = _source_windows(ranges, None if legacy_single else sp,
                                  diarize)
        cached = _cached_words_for_windows(sp, windows, "scribe_v2",
                                           resolved_lang, diarize)
        if cached is None:
            return None  # cache miss → caller must transcribe
        words = normalize_words(cached, script, diarize)
        words_by_source[None if legacy_single else sp] = words

    if not any(words_by_source.values()):
        return None

    # Same script, same correction. It is applied here rather than baked into
    # the cache so a re-split still costs nothing, and so that clearing the
    # script field genuinely clears it instead of leaving corrected words
    # frozen in the cache.
    if ref_script:
        words_by_source = _apply_ref_script(words_by_source, ref_script)

    cues = build_and_remap_cues(words_by_source, max_chars, max_lines, max_secs,
                                ranges, include_punct, cps, min_dur, max_words,
                                resolved_lang, audio_path)
    fps = ranges[0]["fps"] if ranges else 24.0
    if write and cues:
        with open(srt_output, "w", encoding="utf-8") as f:
            f.write(to_srt(cues))
        try:
            with open(srt_output + ".cap", "w", encoding="utf-8") as f:
                f.write(to_caption_sidecar(cues, fps, load_speaker_colors()))
        except Exception as e:
            print("WARNING: could not write caption sidecar: %s" % e)
    return cues, fps


def main_sync(args):
    """Entry point for action="sync": re-time an existing SRT to match the
    audio, keeping its text unchanged. args = [audio_path, srt_input_path,
    srt_output_path, lang_code, diarize]."""
    if len(args) < 3:
        print("ERROR: sync args file must contain audio_path, srt_input_path, srt_output_path")
        sys.exit(1)
    audio_path = args[0]
    srt_input_path = args[1]
    srt_output_path = args[2]
    lang_code = args[3] if len(args) > 3 and args[3] else HINDI_LANG_CODE
    diarize = (args[4] if len(args) > 4 and args[4] else "0") == "1"

    _progress(15, "Loading configuration...")
    load_dotenv()

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ELEVENLABS_API_KEY not set. Add it to " + os.path.join(PIPELINE_DIR, ".env"))
        sys.exit(1)
    if not os.path.exists(audio_path):
        print("ERROR: Audio file not found: " + audio_path)
        sys.exit(1)
    if not os.path.exists(srt_input_path):
        print("ERROR: SRT file not found: " + srt_input_path)
        sys.exit(1)

    _progress(25, "Loading modules...")
    from elevenlabs import ElevenLabs
    client = ElevenLabs(api_key=api_key)

    _progress(40, "Transcribing audio for alignment...")
    try:
        cues = sync_srt_timing(srt_input_path, audio_path, lang_code, diarize,
                               client)
    except AlignmentFailed as e:
        # A refusal, not a crash: the transcription worked, the SRT simply does
        # not belong to this audio. Say which, and write nothing.
        print("\nERROR: " + str(e), flush=True)
        sys.exit(1)
    if not cues:
        print("ERROR: could not align any cues — check that the SRT text matches the audio.")
        sys.exit(1)

    _progress(90, "Writing synced SRT...")
    with open(srt_output_path, "w", encoding="utf-8") as f:
        f.write(to_srt(cues))

    print("OK: " + str(len(cues)) + " cues re-timed and written to " + srt_output_path)
    _progress(100, "Done")


def main():
    # Prefer --args-file: on Windows, cmd.exe mangles non-ASCII argv
    # (e.g. curly apostrophe U+2019) by re-encoding through the system
    # codepage. Reading args from a UTF-8 file avoids that entirely.
    if len(sys.argv) >= 3 and sys.argv[1] == "--args-file":
        with open(sys.argv[2], encoding="utf-8") as af:
            args = [line.rstrip("\r\n") for line in af]
        # "SYNC" sentinel on line 1 routes to the re-time-existing-SRT flow
        # instead of the normal transcribe-from-scratch flow below — kept as
        # one args-file-reading codepath rather than a second argv branch.
        if args and args[0] == "SYNC":
            main_sync(args[1:])
            return
        if len(args) < 2:
            print("ERROR: args file must contain at least audio_path and srt_output")
            sys.exit(1)
        audio_path = args[0]
        srt_output = args[1]
        max_chars = int(args[2]) if len(args) > 2 and args[2] else 20
        max_lines = int(args[3]) if len(args) > 3 and args[3] else 1
        max_secs = float(args[4]) if len(args) > 4 and args[4] else 2.0
        ranges_path = args[5] if len(args) > 5 and args[5] else None
        include_punct = args[6] if len(args) > 6 and args[6] else "1"
        lang_code = args[7] if len(args) > 7 and args[7] else HINDI_LANG_CODE
        diarize = (args[8] if len(args) > 8 and args[8] else "0") == "1"
        cps     = float(args[9]) if len(args) > 9 and args[9] else 20.0
        min_dur = float(args[10]) if len(args) > 10 and args[10] else 0.4
        max_words = int(args[11]) if len(args) > 11 and args[11] else 0
        ref_script = args[12] if len(args) > 12 and args[12] else None
    elif len(sys.argv) < 3:
        print("Usage: transcribe.py <audio_path> <srt_output_path> [max_chars] [max_lines] [max_secs]")
        print("   or: transcribe.py --args-file <path>")
        sys.exit(1)
    else:
        audio_path = sys.argv[1]
        srt_output = sys.argv[2]
        max_chars = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        max_lines = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        max_secs = float(sys.argv[5]) if len(sys.argv) > 5 else 2.0
        ranges_path = sys.argv[6] if len(sys.argv) > 6 else None
        include_punct = sys.argv[7] if len(sys.argv) > 7 else "1"
        lang_code = sys.argv[8] if len(sys.argv) > 8 else HINDI_LANG_CODE
        diarize = (sys.argv[9] if len(sys.argv) > 9 else "0") == "1"
        cps     = float(sys.argv[10]) if len(sys.argv) > 10 else 20.0
        min_dur = float(sys.argv[11]) if len(sys.argv) > 11 else 0.4
        max_words = int(sys.argv[12]) if len(sys.argv) > 12 else 0
        ref_script = sys.argv[13] if len(sys.argv) > 13 else None

    _progress(15, "Loading configuration...")
    load_dotenv()

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ELEVENLABS_API_KEY not set. Add it to " + os.path.join(PIPELINE_DIR, ".env"))
        sys.exit(1)

    if not os.path.exists(audio_path):
        print("ERROR: Audio file not found: " + audio_path)
        sys.exit(1)

    _progress(25, "Loading modules...")
    from elevenlabs import ElevenLabs
    client = ElevenLabs(api_key=api_key)

    # Language from the form selection; ELEVENLABS_LANGUAGE env var overrides
    # as a manual escape hatch. Pinning a language makes the API write that
    # language's script AND turns on the Latin→script safety net below, so the
    # SRT is guaranteed single-script — spoken English included
    # (fast food → फास्ट-फूड / ফাস্ট ফুড). Auto-detect infers the target from
    # the transcript, so code-switched English still lands in the right script.
    resolved_lang = (os.environ.get("ELEVENLABS_LANGUAGE", "").strip()
                     or lang_code or HINDI_LANG_CODE)
    script = script_for_lang(resolved_lang)
    print("Language: %s (script=%s, diarize=%s, cps=%g, min_dur=%g)"
          % (resolved_lang, script, diarize, cps, min_dur))

    def _normalize_words(raw_words):
        return normalize_words(raw_words, script, diarize)

    def _transcribe_file(path, windows=None):
        return fetch_words_ranged(path, windows, resolved_lang, diarize,
                                  client)

    ranges = read_clip_ranges(ranges_path)

    # Collect unique source files from ranges, preserving timeline order so
    # progress reporting is stable. Falls back to audio_path when ranges have
    # no src_path (legacy 5-field format) or no ranges file exists.
    unique_sources = []
    seen = set()
    for r in ranges:
        sp = r.get("src_path")
        if sp and sp not in seen:
            seen.add(sp)
            unique_sources.append(sp)

    words_by_source = {}
    if unique_sources:
        n = len(unique_sources)
        for i, sp in enumerate(unique_sources):
            _progress(40 + int(40 * i / n), "Transcribing %d/%d..." % (i + 1, n))
            if not os.path.exists(sp):
                print("WARNING: source file missing, skipping: " + sp)
                words_by_source[sp] = []
                continue
            words_by_source[sp] = _normalize_words(
                _transcribe_file(sp, _source_windows(ranges, sp, diarize)))
    else:
        # Legacy single-audio path: no ranges or no source paths in ranges.
        # Those rows still carry usable trims, so pass None to take the
        # windows from all of them.
        _progress(40, "Transcribing audio...")
        words_by_source[None] = _normalize_words(
            _transcribe_file(audio_path,
                             _source_windows(ranges, None, diarize)))

    _progress(80, "Building subtitles...")

    if not any(words_by_source.values()):
        print("ERROR: no word data from any source.")
        sys.exit(1)

    # Reference script, applied AFTER the transcript cache and never before it.
    # The cache is keyed on the audio, not on the settings, so that changing a
    # split setting re-splits for free instead of re-paying for the API — a
    # script must therefore change what is BUILT from the words, never what is
    # stored. (See also resplit(), which has to do the same thing.)
    if ref_script:
        words_by_source = _apply_ref_script(words_by_source, ref_script)

    cues = build_and_remap_cues(words_by_source, max_chars, max_lines, max_secs,
                                ranges, include_punct, cps, min_dur, max_words,
                                resolved_lang, audio_path)
    if not cues:
        print("ERROR: No subtitle cues generated.")
        sys.exit(1)

    _progress(95, "Finalizing...")
    with open(srt_output, "w", encoding="utf-8") as f:
        f.write(to_srt(cues))

    # Caption sidecar (per-word timing + per-speaker colour) next to the SRT.
    # The Resolve-side importer reads it for the per-speaker colouring.
    # Best-effort: a failure here must never break the core SRT output.
    try:
        fps = ranges[0]["fps"] if ranges else 24.0
        speaker_colors = load_speaker_colors()
        with open(srt_output + ".cap", "w", encoding="utf-8") as f:
            f.write(to_caption_sidecar(cues, fps, speaker_colors))
    except Exception as e:
        print("WARNING: could not write caption sidecar: %s" % e)

    print("OK: " + str(len(cues)) + " cues written to " + srt_output)
    _progress(100, "Done")


def _is_tls_trust_failure(exc):
    """True when exc, or anything it wraps, is a certificate-verification error.

    The SDK's transport re-raises the ssl error as httpx.ConnectError, so the
    interesting exception is never the outermost one — walk the __cause__ /
    __context__ chain. Type check first, string match as a backstop for
    transports that stringify the ssl error instead of chaining it.
    """
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, ssl.SSLError):
            return True
        if "CERTIFICATE_VERIFY_FAILED" in "%s %s" % (type(exc).__name__, exc):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _explain(exc):
    """Turn an exception into one actionable line, or None to fall back to the
    raw traceback.

    The ElevenLabs SDK raises ApiError with the whole HTTP response attached -
    headers, trace ids, the lot. Dumped straight into a dialog that is what
    buries the one sentence that matters ("Invalid API key") under 400
    characters of noise.
    """
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    detail = body.get("detail") if isinstance(body, dict) else None
    code = detail.get("code") if isinstance(detail, dict) else None
    msg = detail.get("message") if isinstance(detail, dict) else None
    env = os.path.join(PIPELINE_DIR, ".env")

    if status == 401:
        return ("ElevenLabs rejected the API key.\n\n"
                "The key in %s is no longer valid - it was most likely "
                "regenerated or revoked. Create a new key at\n"
                "https://elevenlabs.io/app/settings/api-keys\n"
                "and replace the ELEVENLABS_API_KEY line in that file."
                % env)
    if status == 429:
        return ("ElevenLabs is rate limiting this account, or the character "
                "quota for the month is used up.\n\n"
                "Check usage at https://elevenlabs.io/app/usage, then retry.")
    if status == 403:
        return ("ElevenLabs refused this request (403).\n\n%s\n\n"
                "The key is valid but the account may not have access to "
                "speech-to-text." % (msg or code or ""))
    if status is not None and 500 <= int(status) < 600:
        return ("ElevenLabs had a server error (%s). This is on their end - "
                "wait a moment and run it again." % status)
    if status is not None:
        return "ElevenLabs returned HTTP %s.\n\n%s" % (status, msg or code or "")
    if _is_tls_trust_failure(exc):
        return ("Could not verify the secure connection to ElevenLabs.\n\n"
                "This machine's network is inspecting HTTPS traffic - a "
                "corporate proxy or antivirus is re-signing every connection "
                "with its own certificate. Your browser trusts that "
                "certificate; Python does not.\n\n"
                "Fix: run setup.bat again. It installs the 'truststore' "
                "package, which makes Python use the Windows certificate "
                "store.\n\n"
                "If it still fails, ask IT for the proxy's root CA file "
                "(.cer/.pem) and set the SSL_CERT_FILE environment variable "
                "to its full path.")
    if isinstance(exc, (OSError,)) and getattr(exc, "errno", None) is not None:
        return None
    return None


if __name__ == "__main__":
    # A bare traceback here reaches the user as the body of an error dialog, so
    # anything we can describe plainly is described plainly. Unrecognised
    # failures still print the full traceback — better a wall of text than a
    # swallowed error.
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.exit(130)                                 # cancelled, not failed
    except BaseException as exc:                      # noqa: BLE001
        import traceback
        friendly = None
        try:
            friendly = _explain(exc)
        except Exception:
            friendly = None
        if friendly:
            print("\nERROR: " + friendly, flush=True)
        else:
            print("\nERROR: %s: %s" % (type(exc).__name__, exc), flush=True)
            traceback.print_exc()
        sys.exit(1)
