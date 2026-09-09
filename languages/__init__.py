"""Per-language segmentation data for the supported Indian languages.

One module per language, plus scripts.py for what belongs to a writing system
rather than to a language. This package is DATA ONLY — there is deliberately no
per-language logic anywhere in it. All 13 languages run the same splitter in
transcribe.py; what differs between them is which words are in which table.

That is the whole design rule, and it is worth stating plainly because the
obvious alternative is worse: if each language owned its own segmentation code,
one algorithm would exist in fourteen drifting copies, and a fix to a shared
budget (as the akshara-width fix was) would have to be made fourteen times
instead of once.

To add a word to a language, edit that language's file — nothing else.
To add a language, write its module and add it to LANGUAGES below.


── Function words: which words may not START a cue, which may not END one ───

Every Indian language builds its phrases with short function words that are
grammatically welded to a neighbour, and a cue boundary dropped between them
reads as a mistake even when the timing is perfect:

  BIND_BACK — completes the word before it, so a cue must never OPEN with one
    and one must never stand alone in a cue. Two families:
      • auxiliaries / copulas: है था होगा (hi), ছিল আছে (bn), இருக்கிறது (ta),
        ఉంది (te), ಇದೆ (kn), ഉണ്ട് (ml), છે (gu), ਹੈ (pa), ଅଛି (or), ہے (ur)
      • postpositions, case markers and clitic particles, which are written as
        separate words in the Indo-Aryan languages: का की के को में से (hi),
        এর কে তে থেকে (bn), નો ની ને માં (gu), ਦਾ ਦੀ ਨੂੰ ਵਿੱਚ (pa), کا کی میں (ur)
    The Dravidian languages suffix their case markers onto the noun, so their
    lists are mostly auxiliaries, quotatives (என்று, అని, ಎಂದು, എന്ന്) and
    particles (தான், కూడా, ಮಾತ್ರ).

  BIND_FWD — opens the clause that follows, so a cue should not END with one:
    और कि क्योंकि लेकिन (hi), এবং কিন্তু যদি (bn), மற்றும் ஆனால் (ta),
    మరియు కానీ (te), ಮತ್ತು ಆದರೆ (kn), എന്നാൽ പക്ഷേ (ml), અને પણ (gu),
    ਅਤੇ ਪਰ (pa), ଏବଂ କିନ୍ତୁ (or), اور لیکن (ur)

Tables are per language and unioned per script, because the language is not
always known (auto-detect) and a script pins the candidate languages anyway.
The union is why a word ambiguous across two languages sharing a script (Hindi
particle "तो" vs Marathi pronoun "तो") is treated as bind-back for both: it
costs at most a slightly different boundary, and passing ``lang`` into
build_cues narrows the lookup to that language's own table.

A word listed in both tables for a language is treated as bind-back — that is
the stronger constraint, and the reason Hindi "पर" (postposition "on", but also
"but") stays out of BIND_FWD.


── VERB_END: clause ends the function-word tables cannot see ────────────────

The BIND tables work on whole tokens, which is the right shape for the
Indo-Aryan languages: they write their auxiliaries and postpositions as
separate words, so "समझा रहा हूँ" hands the splitter three tokens to reason
about and the tables catch two of them.

The Dravidian languages hand it one. They suffix the whole finite ending onto
the verb stem — ಅರ್ಥಮಾಡಿಕೊಳ್ಳಬೇಕು, అర్థం చేసుకోవాలి, புரிந்துகொள்ள வேண்டும்,
മനസ്സിലാക്കണം — and they suffix their case markers onto the noun. A Kannada
clause therefore routinely contains NO standalone function word at all:

    ನಾವು ತೆಗೆದುಕೊಳ್ಳುವ ನಿರ್ಧಾರಗಳು ಸ್ಪಷ್ಟವಾಗಿ ಇರುತ್ತವೆ

Every token there is a content word. _best_cut scores every candidate boundary
identically (no punctuation, no bind penalty), so the only term left with any
gradient is _W_FILL — and because it rises monotonically and ties go to the
later cut, the boundary lands exactly where the budget ran out. That is why
Kannada cues broke mid-clause even once the budget itself was measured
correctly: the scorer had nothing to prefer.

These languages are strictly verb-final, which hands us the signal the tables
miss: a FINITE verb form ends its clause, so the boundary immediately after one
is a genuine clause boundary and deserves the same credit as a comma. The
ending is inside the word, so it has to be matched as a suffix.

Suffixes are deliberately long. A short one (Kannada "ತು", Malayalam "ും")
would fire on ordinary nouns; the tense/person endings are distinctive enough
that a noun rarely collides with them, and the ones most at risk are left out
rather than guessed at. A false positive costs little in any case — it prefers
one mid-clause cut over another, which is where the splitter already was —
while a true positive replaces a budget-driven break with a clause-driven one.

Only the verb-final languages define VERB_END. The others write the same
information as separate tokens the BIND tables already see, so reading their
word endings as clause ends too would double-count.
"""

from . import (assamese, bengali, gujarati, hindi, kannada, malayalam,
               marathi, nepali, odia, punjabi, sanskrit, tamil, telugu, urdu)
from . import scripts

# Every supported language. Order is alphabetical by module and carries no
# meaning: the tables below are dicts and sets, and the per-script unions are
# order-independent.
LANGUAGES = (assamese, bengali, gujarati, hindi, kannada, malayalam,
             marathi, nepali, odia, punjabi, sanskrit, tamil, telugu, urdu)

# ── Assembled tables, in the shape transcribe.py consumes ───────────────────
# Keyed by the language's 639-3 table key ("hin", "kan", …).
BIND_BACK_RAW = {m.KEY: m.BIND_BACK for m in LANGUAGES}
BIND_FWD_RAW = {m.KEY: m.BIND_FWD for m in LANGUAGES}

# Language table key → script id, so a language hint is only trusted for tokens
# actually written in that language's script.
FW_LANG_SCRIPT = {m.KEY: m.SCRIPT for m in LANGUAGES}

# ISO 639-1 / 639-3 spellings the UI and the Lua side may send → table key.
FW_LANG_ALIAS = {code: m.KEY for m in LANGUAGES for code in m.CODES}

# VERB_END is keyed by SCRIPT, not by language: it is matched against a token
# whose script is known but whose language often is not. Unioned, for the same
# reason the BIND tables are — two languages sharing a script must both be
# served when auto-detect cannot say which one this is.
VERB_END_RAW = {}
for _m in LANGUAGES:
    _sfx = getattr(_m, "VERB_END", None)
    if _sfx:
        VERB_END_RAW[_m.SCRIPT] = tuple(VERB_END_RAW.get(_m.SCRIPT, ())) + tuple(_sfx)
del _m, _sfx

# A language's KEY must be reachable from its own CODES, or a pinned language
# hint would silently fall back to the script union.
for _m in LANGUAGES:
    assert _m.KEY in _m.CODES, "%s: KEY %r missing from CODES" % (_m.__name__, _m.KEY)
    assert _m.SCRIPT in dict(scripts.SCRIPT_RANGES), \
        "%s: unknown script %r" % (_m.__name__, _m.SCRIPT)
del _m
