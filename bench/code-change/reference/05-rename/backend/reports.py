"""Monthly refund figures for the ops review."""
from refunds import requires_sign_off


def count_large(refunds):
    """How many refunds needed approval this month."""
    return len(list(filter(requires_sign_off, refunds)))
