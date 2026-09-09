"""Assamese. Indo-Aryan, Bengali script.

Data only: no logic lives in this package. transcribe.py reads these tables
and applies the same segmentation rules to every language.
"""

KEY    = "asm"
SCRIPT = "beng"
CODES  = ("as", "asm")

BIND_BACK = (
    "আছে", "আছো", "আছোঁ", "আছিল", "আছিলো", "হয়", "হ'ব", "হৈছে",
    "নাই", "নহয়", "পাৰে", "পাৰিব", "কৰে", "কৰিব", "লাগে", "উচিত",
    "ৰ", "ক", "ত", "লৈ", "পৰা", "সৈতে", "বাবে", "মাজত", "লগত",
    "বিষয়ে", "অনুসৰি", "কাষত", "দৰে",
    "ও", "ই", "টো", "টি", "খন", "জন", "বোৰ",
)

BIND_FWD = ("আৰু", "বা", "অথবা", "কিন্তু", "যদি", "কিয়নো", "তেন্তে",
            "যেতিয়া", "যি", "সেয়েহে", "যদিও")
