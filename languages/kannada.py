"""Kannada. Dravidian, Kannada script.

Data only: no logic lives in this package. transcribe.py reads these tables
and applies the same segmentation rules to every language.
"""

KEY    = "kan"
SCRIPT = "knda"
CODES  = ("kn", "kan")

BIND_BACK = (
    "ಇದೆ", "ಇವೆ", "ಇದ್ದಾರೆ", "ಇದ್ದಾನೆ", "ಇತ್ತು", "ಇರುತ್ತದೆ", "ಇರಬೇಕು",
    "ಆಗಿದೆ", "ಆಗಿತ್ತು", "ಆಗುತ್ತದೆ", "ಆಯಿತು",
    "ಇಲ್ಲ", "ಅಲ್ಲ", "ಬೇಕು", "ಬೇಡ", "ಸಾಧ್ಯ", "ಮಾಡಬೇಕು",
    "ಎಂದು", "ಎಂಬ", "ಅಂತ", "ಎನ್ನುವ",
    "ಗೆ", "ಗೂ", "ಗಾಗಿ", "ಇಂದ", "ಒಂದಿಗೆ", "ಬಗ್ಗೆ", "ಮೇಲೆ", "ವರೆಗೆ",
    "ಕೂಡ", "ಮಾತ್ರ", "ಸಹ",
    "ಇದ್ದೇನೆ", "ಇದ್ದೇವೆ", "ಮೂಲಕ", "ಇಲ್ಲದೆ", "ಹತ್ತಿರ", "ಪ್ರಕಾರ",
    # Relational nouns doing postposition duty. Kannada suffixes its case
    # markers onto the noun, so these are most of what is left standing as
    # its own token — and their absence was visible: "ಯೋಚಿಸುವ ಮೊದಲು"
    # ("before thinking") was being split between two cues.
    "ಮೊದಲು", "ನಂತರ", "ಬಳಿಕ", "ಒಳಗೆ", "ಹೊರಗೆ", "ಕೆಳಗೆ", "ಹಿಂದೆ",
    "ನಡುವೆ", "ಸುತ್ತ", "ಕಡೆ", "ಕಡೆಗೆ", "ಜೊತೆ", "ಜೊತೆಗೆ", "ಸಂಗಡ",
    "ಬದಲು", "ಬದಲಾಗಿ", "ಹೊರತು", "ಹೊರತಾಗಿ", "ಅಂತೆ", "ಹಾಗೆ",
)

BIND_FWD = ("ಮತ್ತು", "ಅಥವಾ", "ಆದರೆ", "ಏಕೆಂದರೆ", "ಆದ್ದರಿಂದ", "ಹಾಗಾಗಿ",
            "ಅಂದರೆ", "ಆಗ", "ಮೇಲಾಗಿ", "ಒಂದುವೇಳೆ", "ಆದಾಗ್ಯೂ")

# Kannada: present/habitual -ತ್ತ- + person, the perfect -ಿದ-, the past -ಿತು,
# and the modals, which are a suffixed verb of their own.
VERB_END = ("ತ್ತದೆ", "ತ್ತವೆ", "ತ್ತಾನೆ", "ತ್ತಾಳೆ", "ತ್ತಾರೆ", "ತ್ತೇನೆ", "ತ್ತೇವೆ",
            "ತ್ತಿದೆ", "ತ್ತಿವೆ", "ತ್ತಿದ್ದಾರೆ",
            "ಿದೆ", "ಿವೆ", "ಿದ್ದಾರೆ", "ಿದ್ದಾನೆ", "ಿದ್ದೇನೆ", "ಿದ್ದೇವೆ",
            "ಿತು", "ಾಯಿತು", "ಿದನು", "ಿದಳು", "ಿದರು", "ಿದೆವು",
            "ಬೇಕು", "ಬಹುದು", "ಬಾರದು", "ಬೇಡ", "ಇಲ್ಲ", "ಿಲ್ಲ")
