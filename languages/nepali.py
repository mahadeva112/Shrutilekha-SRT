"""Nepali. Indo-Aryan, Devanagari.

Data only: no logic lives in this package. transcribe.py reads these tables
and applies the same segmentation rules to every language.
"""

KEY    = "nep"
SCRIPT = "dev"
CODES  = ("ne", "nep")

BIND_BACK = (
    "छ", "छन्", "छु", "छौ", "छिन्", "छैन", "छैनन्",
    "थियो", "थिए", "थिएन", "हो", "होइन", "भयो", "भएको", "हुन्छ", "हुन्",
    "गर्छ", "गर्छन्", "सक्छ", "पर्छ", "पर्दैन",
    "को", "का", "की", "ले", "लाई", "मा", "बाट", "सँग", "देखि", "सम्म",
    "पनि", "नै", "बारे", "बिना", "अनुसार", "नजिक",
)

BIND_FWD = ("र", "वा", "अथवा", "कि", "किनभने", "तर", "यदि", "जब",
            "त्यसैले", "जो", "जुन", "तापनि")
