"""Malayalam. Dravidian, Malayalam script.

Data only: no logic lives in this package. transcribe.py reads these tables
and applies the same segmentation rules to every language.
"""

KEY    = "mal"
SCRIPT = "mlym"
CODES  = ("ml", "mal")

BIND_BACK = (
    "ഉണ്ട്", "ഉണ്ടായിരുന്നു", "ഉണ്ടാകും", "ആണ്", "ആയിരുന്നു", "ആകുന്നു",
    "ആയി", "ആകും", "ഇല്ല", "അല്ല", "വേണം", "വേണ്ട", "കഴിയും",
    "കഴിഞ്ഞു", "ചെയ്യണം", "പറ്റും",
    "എന്ന്", "എന്ന", "എന്നു", "കൂടി", "മാത്രം", "പോലെ", "വരെ", "മുതൽ",
    "കുറിച്ച്", "വേണ്ടി", "ഒപ്പം", "ആയിട്ട്",
    "വഴി", "ഇല്ലാതെ", "അടുത്ത്", "പ്രകാരം",
)

BIND_FWD = ("എന്നാൽ", "പക്ഷേ", "അല്ലെങ്കിൽ", "കാരണം", "എങ്കിൽ", "അതിനാൽ",
            "അതുകൊണ്ട്", "അപ്പോൾ", "കൂടാതെ", "എന്നിരുന്നാലും", "അതായത്")

# Malayalam: -ുന്നു present, -ി / -ു past (too short to use), the -ണം
# obligative, and the negatives.
VERB_END = ("ുന്നു", "ുന്നുണ്ട്", "ുണ്ട്", "ണം", "ിക്കും", "ിരിക്കും",
            "ായിരുന്നു", "ിയിരുന്നു", "ില്ല", "ുകയാണ്", "ുമായിരുന്നു")
