from bs4 import BeautifulSoup
from slugify import slugify

# Illustrative sample payload -- in production this task would read raw
# landed tickets from a Snowflake table via `session` instead.
RAW_TICKETS = [
    {
        "subject": "Payment Failed -- Order #4821",
        "body_html": "<p>My <b>card</b> was declined twice.</p>",
    },
    {
        "subject": "  Login issue on mobile app  ",
        "body_html": "<div>Can't log in since <i>yesterday</i>.</div>",
    },
]


def run(session):
    normalized = []
    for ticket in RAW_TICKETS:
        body = BeautifulSoup(ticket["body_html"], "html.parser").get_text(" ", strip=True)
        normalized.append({"key": slugify(ticket["subject"]), "body": body})
    return f"ingested {len(normalized)} ticket(s): {normalized}"
