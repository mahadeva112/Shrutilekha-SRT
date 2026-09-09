"""Writing-system data, shared by every language that uses it.

Data only: no logic lives in this package. transcribe.py reads these tables.

This module holds what belongs to a SCRIPT rather than to a language, which is
most of what stops the per-language files from having to repeat each other.
Devanagari serves Hindi, Marathi, Nepali and Sanskrit; the Bengali script serves
Bengali and Assamese; the danda ends a sentence in nearly all of them. None of
that has a single owner, so it lives here.
"""

# ── Script ranges ───────────────────────────────────────────────────────────
# Every script the supported languages are written in. Two different questions
# get asked about a token's script and they want different answers — which font
# the cue needs, and which language's grammar applies — but that distinction
# belongs to the functions that read this table, so it is documented there
# (_char_script / _token_script in transcribe.py) rather than repeated here.
#
# IMPORTANT: several codepoints sit inside a script's block but are shared —
# danda ।(U+0964) / double danda ॥(U+0965) are used by nearly every Indic
# script, the Vedic tone marks U+0951–U+0952 likewise, and the Arabic block
# holds the punctuation Urdu shares with Arabic (، ؛ ؟ ۔). None of them may
# decide a token's script.
SCRIPT_RANGES = (
    # Devanagari — Hindi, Marathi, Nepali, Sanskrit, Konkani, Maithili, Dogri,
    # Bodo. Core, Extended, Extended-A and the Vedic Extensions.
    ("dev",  ((0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x11B00, 0x11B09),
              (0x1CD0, 0x1CFF))),
    ("beng", ((0x0980, 0x09FF),)),                 # Bengali, Assamese, Manipuri
    ("guru", ((0x0A00, 0x0A7F),)),                 # Gurmukhi — Punjabi
    ("gujr", ((0x0A80, 0x0AFF),)),                 # Gujarati
    ("orya", ((0x0B00, 0x0B7F),)),                 # Odia
    ("taml", ((0x0B80, 0x0BFF), (0x11FC0, 0x11FFF))),   # Tamil + supplement
    ("telu", ((0x0C00, 0x0C7F),)),                 # Telugu
    ("knda", ((0x0C80, 0x0CFF),)),                 # Kannada
    ("mlym", ((0x0D00, 0x0D7F),)),                 # Malayalam
    ("sinh", ((0x0D80, 0x0DFF),)),                 # Sinhala
    # Arabic — Urdu, and Sindhi/Kashmiri when written in Perso-Arabic.
    ("arab", ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
              (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    ("mtei", ((0xAAE0, 0xAAFF), (0xABC0, 0xABFF))),     # Meetei Mayek
    ("olck", ((0x1C50, 0x1C7F),)),                 # Ol Chiki — Santali
)

# Script-neutral codepoints that live inside a script block (see above).
NEUTRAL_CPS = frozenset((
    0x0964, 0x0965,          # danda, double danda — pan-Indic
    0x0951, 0x0952,          # Vedic tone marks — pan-Indic
    0x060C, 0x061B, 0x061F,  # Arabic comma, semicolon, question mark
    0x06D4,                  # Urdu full stop ۔
    0x066B, 0x066C,          # Arabic decimal/thousands separators
    0x0640,                  # tatweel — a joining glyph, not a letter
))

# ── Conjunct width ──────────────────────────────────────────────────────────
# A virama links the consonant after it into the cluster before it. What that
# conjunct then costs in line width depends on how the script builds it, which
# is the difference between the two tables. See _vlen in transcribe.py.
#
# Kannada and Telugu stack a conjunct VERTICALLY — the second consonant is a
# subscript under the first, so ತ್ತ is one akshara wide and costs 1.
STACKING_VIRAMA = frozenset((
    0x0C4D,   # Telugu
    0x0CCD,   # Kannada
))
# Devanagari and its neighbours join a conjunct HORIZONTALLY — क्या is a single
# cluster but a visibly wide one, so it costs 2 rather than 1. Counting it as one
# akshara would under-state the line and let the text overflow the frame.
JOINING_VIRAMA = frozenset((
    0x094D,   # Devanagari
    0x09CD,   # Bengali, Assamese
    0x0A4D,   # Gurmukhi
    0x0ACD,   # Gujarati
    0x0B4D,   # Odia
    0x0D4D,   # Malayalam
))
# Tamil's pulli (U+0BCD) is in neither table. It suppresses a vowel but does not
# ligate at all — க்க is two separate clusters — so it neither links nor adds
# width, and falls through to being skipped as the plain mark it is.

# ── Transliteration: Devanagari as the pivot script ─────────────────────────
# NOTE: the offset alone is not enough, and the two tables after it are why.
# Getting a Devanagari spelling into another script's CODEPOINTS is arithmetic;
# getting it into that script's ORTHOGRAPHY needs a handful of corrections that
# are statements about the language, not about Unicode. They are here rather
# than in transcribe.py because they are data about writing systems, which is
# what this module is for.
# The Indic blocks are laid out in PARALLEL — the same offset within each block
# is the same letter. So a string in Devanagari becomes the same string in
# another Indic script by adding a fixed number to every codepoint:
#
#     ब्रेड  ->  ಬ್ರೇಡ     (cp - 0x0900 + 0x0C80)
#
# That is what lets the one pronunciation-derived dictionary that ships for
# Devanagari (data/translit_dev.json.gz, 117k words) serve every script here,
# instead of each script needing a dictionary and a phonetic engine of its own.
# transcribe.py's _fold_from_dev() does the arithmetic; these are its tables.
#
# Bengali is deliberately ABSENT: it has its own dictionary and its own rule
# table, and its block is missing enough Devanagari letters that the offset
# would be the wrong tool for spelling a word into it from scratch.
#
# The block base each of these shifts to is NOT repeated here — it is the start
# of the script's first range in SCRIPT_RANGES above, and transcribe.py reads it
# off there, so the two cannot drift apart.
TRANSLIT_VIA_DEV = frozenset((
    "guru",   # Gurmukhi — Punjabi
    "gujr",   # Gujarati
    "orya",   # Odia
    "taml",   # Tamil
    "telu",   # Telugu
    "knda",   # Kannada
    "mlym",   # Malayalam
))

# Letters to rewrite BEFORE the offset, because the target block has nothing at
# that position. Checked against every Devanagari character the two
# transliteration layers can emit — the 117k dictionary and the phonetic rules
# together — so a miss here is a character that would land on an unassigned
# codepoint and render as tofu.
#
# ऑ/ॉ is the English "aw" of doctor, call, office. Devanagari has a candra-O
# for it; among these scripts only Gujarati does too. The rest do not agree on
# how to write the sound, so there is no single fold:
#
#   ā   Gurmukhi, Tamil, Telugu, Kannada — ਡਾਕਟਰ, டாக்டர், డాక్టర్, ಡಾಕ್ಟರ್
#   ō   Malayalam — ഡോക്ടർ, ഓഫീസ്
#   —   Odia deletes it: Odia's INHERENT vowel already is /ɔ/, so dropping the
#       matra leaves both the right sound and the right spelling (ଡକ୍ଟର).
#
# The Odia rule is not a guess: the shipped Bengali dictionary already does
# exactly this, and Bengali's inherent vowel is /ɔ/ too — call → কল, all → অল,
# office → অফিস. Short ऒ/ॊ would be wrong everywhere; English /ɔː/ is long.
_AW_LONG_A = {"ऑ": "आ", "ॉ": "ा"}
_AW_LONG_O = {"ऑ": "ओ", "ॉ": "ो"}
_AW_DROP = {"ऑ": "अ", "ॉ": ""}

# Tamil additionally has ONE stop per place of articulation — voicing and
# aspiration are allophonic and simply are not written. க covers ka/kha/ga/gha,
# ப covers pa/pha/ba/bha, and so on. Every voiced and aspirated Devanagari stop
# therefore folds onto its plain unvoiced counterpart before the offset, which
# is how Tamil actually spells English loanwords (bread -> ப்ரேட). The grantha
# letters ஜ ஶ ஷ ஸ ஹ do exist and are left alone, so ja/sha/ha survive intact.
# The nukta is dropped: Tamil has no letter it could qualify.
TRANSLIT_FOLD = {
    "gujr": {},                    # exact 1:1 — Gujarati has the candra vowels
    "guru": dict(_AW_LONG_A),
    "telu": dict(_AW_LONG_A, **{"़": ""}),
    "knda": dict(_AW_LONG_A, **{"़": ""}),
    "mlym": dict(_AW_LONG_O, **{"़": ""}),
    "orya": dict(_AW_DROP, **{"़": ""}),
    "taml": dict(_AW_LONG_A, **{
        "़": "",
        # Tamil writes ONE stop per place of articulation — voicing and
        # aspiration are allophonic and simply are not spelt. க covers
        # ka/kha/ga/gha, ப covers pa/pha/ba/bha, and so on, which is how Tamil
        # really writes English loans (bread → ப்ரெட்).
        "ख": "क", "ग": "क", "घ": "क",
        "ड": "ट",
        "थ": "त", "द": "त", "ध": "त",
        "फ": "प", "ब": "प", "भ": "प",
        # श offsets onto the Grantha ஶ, which is assigned but thin in the fonts
        # SUBTITLE_SCRIPTS prefers; modern Tamil writes /ʃ/ as ஷ.
        "श": "ष",
    }),
}
# The nukta only ever reaches here from ज़ (z). Dropping it yields the plain ja
# letter, which is what these scripts use. Kept for Gurmukhi (ਜ਼ is standard
# Punjabi) and Gujarati.

# Scripts that DELETE a word-final schwa, as Devanagari does. The dictionary's
# values are Devanagari, so they already have no final vowel — डॉक्टर, ब्रेड.
# Every script NOT listed here pronounces that bare final consonant with its
# inherent vowel, turning ब्रेड into /brēḍa/, so the transliterator has to put
# the vowel-killer back: ಬ್ರೇಡ್, బ్రేడ్, ப்ரெட், ബ്രേഡ്, ବ୍ରେଡ୍. 72% of the
# dictionary ends in a bare consonant, so this is not an edge case.
TRANSLIT_DROPS_FINAL_SCHWA = frozenset(("dev", "beng", "gujr", "guru"))

# Malayalam writes a word-final coda consonant as a chillu letter rather than
# consonant + virama: ഡോക്ടർ, not ഡോക്ടര്. Word-final only — word-internally
# the sequence is ambiguous with a legitimate geminate (ന്ന).
MLYM_CHILLU = {"ര": "ർ", "ന": "ൻ", "ല": "ൽ", "ള": "ൾ", "ണ": "ൺ"}

# Gurmukhi does not write a cluster with a visible halant: Punjabi spells
# ਸਕੂਲ, ਡਾਕਟਰ, ਟੈਸਟ. The halant survives only in the subjoined forms, before
# ਹ ਰ ਵ ਯ — which is why ਬ੍ਰੇਡ keeps its ੍ਰ. 60% of the dictionary contains a
# virama, so leaving them all in would misspell most Punjabi output.
GURU_SUBJOINED = frozenset("ਹਰਵਯ")

# Punjabi writes a nasal as tippi ੰ after a short vowel (including the bare
# inherent one) and as bindi ਂ after a long one or an independent vowel. The
# offset always produces bindi, and a bindi sitting on a bare consonant is
# visibly wrong to a Punjabi reader: ਕੰਪਿਊਟਰ, not ਕਂਪਿਊਟਰ.
GURU_BINDI_AFTER = frozenset("ਾੀੇੈੋੌਅਆਇਈਉਊਏਐਓਔ")

# Modern Tamil barely uses the anusvara ஂ and many fonts render it poorly, so
# a nasal is written as the homorganic nasal + pulli instead, chosen by the
# consonant that follows: கம்ப்யூடர் (computer), நம்பர் (number).
TAML_NASAL = (
    ("கஙஹ", "ங்"),
    ("சஜஞஷஸ", "ஞ்"),
    ("டண", "ண்"),
    ("தந", "ந்"),
    ("பம", "ம்"),
)
TAML_NASAL_DEFAULT = "ம்"


# ── Punctuation ─────────────────────────────────────────────────────────────
# Sentence-end punctuation across the supported scripts. A word ending in one
# of these is a "strong" boundary — never carry past it into the same cue when
# avoidable. Indic scripts share the danda ।/॥ (Devanagari, Bengali, Gurmukhi,
# Gujarati, Odia; the southern four normally use the Latin full stop), while
# Urdu has its own full stop ۔ and question mark ؟ — omitting those made every
# Urdu cue boundary look unpunctuated to the splitter.
STRONG_END = ("।", "॥", ".", "?", "!", "？", "！", "۔", "؟", "…")
# Clause-level boundary — weaker, scored below a sentence end. Urdu again uses
# its own comma ، and semicolon ؛.
WEAK_END = (",", ";", ":", "—", "–", "،", "؛", "，", "、")

# Trailing quotes/brackets to look past when testing a word's final character
# ("वाक्य।"" still ends a sentence). Deliberately excludes the ellipsis, which
# is itself a terminator.
END_TRIM = "\"'”’»)]}"

# ── Function-word normalization ─────────────────────────────────────────────
# Characters to strip off a token before a function-word lookup.
FW_STRIP = "।॥.?!,;:—–…،؛؟۔\"“”‘’'()[]{}«»-"

# Characters to delete INSIDE a token before the lookup, so that the spelling
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
FW_IGNORE = frozenset(
    [chr(c) for c in (0x200B, 0x200C, 0x200D,    # ZWSP, ZWNJ, ZWJ
                      0x200E, 0x200F, 0x061C,    # LRM, RLM, ALM (bidi marks)
                      0x0640,                    # tatweel — a joiner, not a letter
                      0x0670,                    # Arabic superscript alef
                      0x093C, 0x09BC, 0x0A3C,    # nukta: Devanagari, Bengali,
                      0x0ABC, 0x0B3C, 0x0CBC)]   #   Gurmukhi, Gujarati, Odia,
                                                 #   Kannada
    + [chr(c) for c in range(0x064B, 0x0653)])   # Arabic vowel points
