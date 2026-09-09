# `languages/`

Per-language segmentation data. **Data only — no logic lives here.**

All 13 languages run the same cue splitter in `transcribe.py`. What differs
between them is which words sit in which table. That is the design rule, and
it is deliberate: if each language owned its own segmentation code, one
algorithm would exist in fourteen drifting copies, and a fix to something
shared (the akshara-width fix, which corrected Kannada, Telugu, Tamil,
Malayalam, Hindi and Bengali at once) would have to be made fourteen times.

## Layout

| file | holds |
|---|---|
| `<language>.py` | that language's `BIND_BACK`, `BIND_FWD`, and `VERB_END` where it applies |
| `scripts.py` | what belongs to a writing system, not a language — script ranges, punctuation, conjunct widths, the marks normalized away before a lookup |
| `__init__.py` | assembles the per-language files into the tables `transcribe.py` reads, and documents the linguistics behind them |

`scripts.py` exists because scripts and languages are not 1:1. Devanagari
serves Hindi, Marathi, Nepali and Sanskrit; the Bengali script serves Bengali
and Assamese. Shared data has no single owner, so it does not go in a language
file.

## The three tables

**`BIND_BACK`** — words that complete the word before them, so a cue may never
*open* with one and one may never stand alone in a cue. Auxiliaries and copulas
(`ಇದೆ`, `है`, `ছিল`, `ہے`), and the postpositions and case markers the
Indo-Aryan languages write as separate tokens (`का`, `में`, `નો`, `ਦਾ`).

**`BIND_FWD`** — words that open the clause that follows, so a cue should not
*end* on one. Conjunctions and subordinators (`ಮತ್ತು`, `और`, `কিন্তু`, `اور`).

**`VERB_END`** — finite verb *endings*, matched as suffixes. Only the four
verb-final Dravidian languages define this. They suffix the whole finite ending
onto the verb stem (`ಅರ್ಥಮಾಡಿಕೊಳ್ಳಬೇಕು`), so a clause can end with no separate
token for `BIND_BACK`/`BIND_FWD` to catch — a Kannada clause routinely contains
no standalone function word at all. Matching the ending recovers the clause
boundary. The other languages write the same information as separate tokens the
BIND tables already see, so giving them a `VERB_END` would double-count.

A word in both `BIND_BACK` and `BIND_FWD` is treated as bind-back: it is the
stronger constraint. That is why Hindi `पर` (postposition "on", but also "but")
stays out of `BIND_FWD`.

## Adding a word

Edit that language's file. Nothing else — `__init__.py` picks it up.

Words are normalized before lookup (NFC, surrounding punctuation stripped,
nukta and zero-width marks removed), so you do not need to add spelling
variants: `पड़ेगा` and `पडेगा` both reach the same entry.

Then run the tests. They sweep every language across 3 speaking rates and 7
budget combinations, asserting invariants like "no cue opens with a
phrase-completing word":

```bash
python test_transcribe.py
```

## Adding a language

1. Write `languages/<name>.py` with `KEY`, `SCRIPT`, `CODES`, `BIND_BACK`,
   `BIND_FWD`, and `VERB_END` if the language is verb-final.
   - `KEY` is the ISO 639-3 code used as the table key.
   - `CODES` is every spelling the UI or the Lua side might send, and **must
     include `KEY` itself** — `__init__.py` asserts this, because otherwise a
     pinned language hint would silently fall back to the script union.
   - `SCRIPT` must already be in `scripts.py`'s `SCRIPT_RANGES`; add it there
     first if the script is new, along with its virama if it has one.
2. Add the module to the `from . import` line and to `LANGUAGES` in
   `__init__.py`.
3. Add a sample sentence to `SAMPLES` in `test_transcribe.py` and its
   never-open words to `NEVER_OPENS`, so the cross-language sweep covers it.

## Adding a word does not need a language hint to work

The tables are unioned per script as well as kept per language, because the
default is auto-detect and the language is often unknown. A Kannada word added
to `kannada.py` is therefore found either way: by the Kannada table when the
language is pinned, or by the Kannada-script union when it is not. The union is
also why a word ambiguous between two languages sharing a script (Hindi
particle `तो` vs Marathi pronoun `तो`) is treated as bind-back for both — it
costs at most a slightly different boundary.
