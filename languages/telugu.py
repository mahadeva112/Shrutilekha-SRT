"""Telugu. Dravidian, Telugu script.

Data only: no logic lives in this package. transcribe.py reads these tables
and applies the same segmentation rules to every language.
"""

KEY    = "tel"
SCRIPT = "telu"
CODES  = ("te", "tel")

BIND_BACK = (
    "ఉంది", "ఉన్నది", "ఉన్నాయి", "ఉన్నాడు", "ఉంది", "ఉన్నారు",
    "ఉంటుంది", "ఉంటాయి", "ఉండాలి", "ఉండేది", "ఉన్న",
    "అయింది", "అవుతుంది", "అవుతాయి", "అయ్యింది",
    "లేదు", "లేవు", "కాదు", "కావు", "చేయాలి", "కూడదు", "గలదు",
    "అని", "అంటే", "అనే", "గా", "కి", "కు", "లో", "నుండి", "నుంచి",
    "తో", "వల్ల", "గురించి", "వరకు", "కోసం", "పైన", "కూడా", "మాత్రమే",
    "ఉన్నాను", "ఉన్నాం", "ద్వారా", "లేకుండా", "దగ్గర", "ప్రకారం",
)

BIND_FWD = ("మరియు", "లేదా", "కానీ", "కాని", "ఎందుకంటే", "అయితే", "ఒకవేళ",
            "అప్పుడు", "కాబట్టి", "ఇంకా", "అందుకే", "అలాగే", "ఐతే")

# Telugu: -ంది / -తుంది / -తాయి present, the -ాలి obligative, and the person
# endings. Written WITHOUT the stem's vowel sign, because the same ending
# follows an independent vowel just as often as a consonant — "ఉంటాయి" ends
# in ంటాయి with no ు anywhere, and requiring one missed it. The bare
# two-akshara person endings -ాము / -ాను are left out: they collide with
# ordinary nouns, and the -తాము / -తాను forms cover the verbs anyway.
VERB_END = ("ంది", "న్నాయి", "తుంది", "తాయి", "ంటుంది", "ంటాయి",
            "తారు", "తాము", "తాను",
            "న్నాను", "న్నాము", "న్నారు", "న్నాడు",
            "ారు", "ాడు", "ాలి", "లేదు", "కాదు")
