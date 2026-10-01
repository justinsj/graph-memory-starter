"""What a refund must satisfy before money moves."""
from config import APPROVAL_THRESHOLD_GBP, EUR_TO_GBP, REFUND_WINDOW_DAYS

TO_GBP = {"GBP": 1.0, "EUR": EUR_TO_GBP}


def needs_approval(amount, currency="GBP"):
    """True when a refund is large enough to need someone's sign-off, in pounds or euros."""
    if currency not in TO_GBP:
        raise ValueError(f"unknown currency {currency}")
    return amount * TO_GBP[currency] > APPROVAL_THRESHOLD_GBP


def validate(refund):
    """A refund needs an order and a positive amount."""
    if not refund.get("order_id") or refund.get("amount", 0) <= 0:
        raise ValueError("a refund needs an order and a positive amount")


def within_window(order_age_days):
    """True while an order is young enough to refund."""
    return order_age_days <= REFUND_WINDOW_DAYS
