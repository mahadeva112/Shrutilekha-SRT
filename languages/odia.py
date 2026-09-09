"""Odia. Indo-Aryan, Odia script.

Data only: no logic lives in this package. transcribe.py reads these tables
and applies the same segmentation rules to every language.
"""

KEY    = "ori"
SCRIPT = "orya"
CODES  = ("or", "ori", "ory", "od")

# Odia. Copulas and the ubiquitous -ଛି progressives, then the postpositions
# and the definite/plural clitics, which Scribe sometimes writes as their
# own token instead of suffixed.
BIND_BACK = (
    "ଅଛି", "ଅଛନ୍ତି", "ଅଛୁ", "ଅଛ",
    "ଥିଲା", "ଥିଲେ", "ଥିଲି", "ଥାଏ",
    "ହୁଏ", "ହେଉଛି", "ହେଉଥିଲା", "ହେବ", "ହୋଇଛି", "ହୋଇଥିଲା",
    "ନାହିଁ", "ନୁହେଁ", "ପାରିବ", "ପାରେ", "ପାରିଲା", "ଉଚିତ",
    "କରେ", "କରିବ", "କରୁଛି", "କରୁଛନ୍ତି",
    "ଯାଏ", "ଯାଇଛି", "ଯାଇଥିଲା", "ଲାଗେ", "ପଡ଼େ",
    # postpositions
    "ର", "ରେ", "କୁ", "ଠାରୁ", "ଠାରେ", "ସହ", "ସହିତ", "ପାଇଁ", "ଲାଗି",
    "ଭିତରେ", "ଭିତରୁ", "ଉପରେ", "ପଛରେ", "ମଧ୍ୟରେ", "ନିକଟରେ",
    "ପର୍ଯ୍ୟନ୍ତ", "ପରେ", "ପୂର୍ବରୁ", "ଦ୍ୱାରା", "ପରି", "ଭଳି",
    "ବିଷୟରେ", "ବିନା", "ଅନୁସାରେ", "ପାଖରେ",
    # clitics: emphasis, "also", the definite marker and the plurals
    "ମଧ୍ୟ", "ହିଁ", "ବି", "ସୁଦ୍ଧା",
    "ଟି", "ଟା", "ଟିଏ", "ଗୁଡ଼ିକ", "ଗୁଡ଼ାକ",
    "ମାନଙ୍କ", "ମାନଙ୍କୁ", "ମାନଙ୍କର",
)

BIND_FWD = ("ଏବଂ", "ଓ", "କିମ୍ବା", "ଅଥବା", "କିନ୍ତୁ", "ପରନ୍ତୁ", "ଯଦି",
            "କାରଣ", "ଯେହେତୁ", "ତେଣୁ", "ଏଣୁ", "ସେଥିପାଇଁ", "ତେବେ",
            "ଯେତେବେଳେ", "ସେତେବେଳେ", "ଯେ", "ଯାହା", "ଯିଏ", "ଯେପରି",
            "ତଥାପି", "ଯଦିଓ")
