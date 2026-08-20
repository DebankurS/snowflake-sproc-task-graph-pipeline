from langdetect import DetectorFactory, detect

# langdetect samples randomly internally; seed it so results are deterministic.
DetectorFactory.seed = 0

# Sample payload; production would read ingest-tickets' output via `session`.
SAMPLE_BODIES = [
    "My card was declined twice.",
    "Impossible de me connecter depuis hier.",
]


def run(session):
    detected = [{"body": body, "lang": detect(body)} for body in SAMPLE_BODIES]
    return f"detected language for {len(detected)} ticket(s): {detected}"
