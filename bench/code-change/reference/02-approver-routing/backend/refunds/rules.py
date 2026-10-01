"""What a refund must satisfy before money moves."""
from config import APPROVAL_THRESHOLD_GBP, DIRECTOR_THRESHOLD_GBP, REFUND_WINDOW_DAYS


def needs_approval(amount_gbp):
    """True when a refund is large enough to need someone's sign-off."""
    return amount_gbp > APPROVAL_THRESHOLD_GBP


def approver_for(amount_gbp):
    """Who must sign a refund off: no one, the Ops Manager, or the Director for the largest."""
    if amount_gbp > DIRECTOR_THRESHOLD_GBP:
        return "Director"
    if needs_approval(amount_gbp):
        return "Ops Manager"
    return None


def validate(refund):
    """A refund needs an order and a positive amount."""
    if not refund.get("order_id") or refund.get("amount", 0) <= 0:
        raise ValueError("a refund needs an order and a positive amount")


def within_window(order_age_days):
    """True while an order is young enough to refund."""
    return order_age_days <= REFUND_WINDOW_DAYS
