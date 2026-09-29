"""Refunds waiting for someone's sign-off."""

PENDING = []


def queue_for_approval(refund):
    """Hold a refund until it is signed off."""
    PENDING.append(refund)
