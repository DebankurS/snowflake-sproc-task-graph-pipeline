from transformers import pipeline

# distilbert-base-uncased-finetuned-sst-2-english -- real fine-tuned weights,
# not a placeholder, fetched from the Hugging Face Hub by model id rather
# than bundled in src/model/ (the ~268MB of weights are too big to commit,
# see README). Built at module scope so the download happens once, at
# procedure initialization, and the same classifier is reused for every
# invocation on a warm sandbox -- not re-downloaded per call. Requires the
# stored procedure's Snowflake EXTERNAL ACCESS INTEGRATION to permit
# outbound HTTPS to huggingface.co (see procedure.yaml).
classifier = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")

# Illustrative sample payload -- in production this would be the
# English-language subset of what detect-language just tagged, read back
# via `session`.
SAMPLE_BODIES = [
    "My card was declined twice, this is unacceptable.",
    "Thanks, the new update fixed it perfectly!",
]


def run(session):
    results = classifier(SAMPLE_BODIES)
    return f"classified {len(results)} ticket(s): {results}"
