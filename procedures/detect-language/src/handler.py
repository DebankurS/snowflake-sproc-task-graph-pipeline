from langdetect import detect

# Illustrative sample payload -- in production this would be the text
# ingest-tickets just wrote out, read back via `session`.
SAMPLE_BODIES = [
    "My card was declined twice.",
    "Impossible de me connecter depuis hier.",
]


def run(session):
    detected = [{"body": body, "lang": detect(body)} for body in SAMPLE_BODIES]
    return f"detected language for {len(detected)} ticket(s): {detected}"
