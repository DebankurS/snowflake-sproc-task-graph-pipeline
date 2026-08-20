from transformers import pipeline

# Built at module scope so weights download once and the classifier is
# reused across invocations on a warm sandbox. Needs the EXTERNAL ACCESS
# INTEGRATION in procedure.yaml for outbound HTTPS to huggingface.co.
classifier = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")

# Sample payload; production would read detect-language's output via `session`.
SAMPLE_BODIES = [
    "My card was declined twice, this is unacceptable.",
    "Thanks, the new update fixed it perfectly!",
]


def run(session):
    results = classifier(SAMPLE_BODIES)
    return f"classified {len(results)} ticket(s): {results}"
