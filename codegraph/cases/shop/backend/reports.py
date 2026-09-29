"""Monthly refund figures for the ops review."""
from refunds import needs_approval


def count_large(refunds):
    """How many refunds needed approval this month."""
    return len(list(filter(needs_approval, refunds)))
