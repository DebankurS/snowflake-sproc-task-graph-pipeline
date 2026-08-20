def run(session):
    # In production this would join classify-sentiment's and
    # extract-entities' output tables on ticket key. Both upstream branches
    # have to finish first -- that's the point of this node.
    return "aggregate-report: joined sentiment + entity signals into ticket_enrichment_summary"
