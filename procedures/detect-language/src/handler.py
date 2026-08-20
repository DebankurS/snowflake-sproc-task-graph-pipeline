from langdetect import DetectorFactory, detect

# langdetect's Naive Bayes filter samples randomly internally; without a
# fixed seed the same input can get a different language code on different
# runs (documented behavior of the library). Downstream nodes key off this
# result, so determinism here matters more than it would standalone.
DetectorFactory.seed = 0

# Illustrative sample payload -- in production this would be the text
# ingest-tickets just wrote out, read back via `session`.
SAMPLE_BODIES = [
    "My card was declined twice.",
    "Impossible de me connecter depuis hier.",
]


def run(session):
    detected = [{"body": body, "lang": detect(body)} for body in SAMPLE_BODIES]
    return f"detected language for {len(detected)} ticket(s): {detected}"
