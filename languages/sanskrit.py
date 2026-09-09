"""Sanskrit. Indo-Aryan, Devanagari.

Data only: no logic lives in this package. transcribe.py reads these tables
and applies the same segmentation rules to every language.
"""

KEY    = "san"
SCRIPT = "dev"
CODES  = ("sa", "san")

# Classical Sanskrit enclitics — postpositive by definition, never initial.
BIND_BACK = ("च", "वा", "एव", "हि", "अपि", "इति", "तु", "खलु", "किल")

BIND_FWD = ("यदि", "यथा", "यत्", "यस्मात्", "तस्मात्", "अथ", "किन्तु", "परन्तु")
