import re

import phonenumbers

ORDER_RE = re.compile(r"#(\d{3,})")

# Sample payload; production would read ingest-tickets' output via `session`.
SAMPLE_BODIES = [
    "My card was declined twice on Order #4821, call me at +1 415 555 0132.",
    "No phone or order number in this one.",
]


def run(session):
    extracted = []
    for body in SAMPLE_BODIES:
        orders = ORDER_RE.findall(body)
        phones = [
            phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
            for match in phonenumbers.PhoneNumberMatcher(body, "US")
        ]
        extracted.append({"orders": orders, "phones": phones})
    return f"extracted entities from {len(extracted)} ticket(s): {extracted}"
