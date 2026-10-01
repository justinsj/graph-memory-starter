"""Refunds waiting for someone's sign-off."""

PENDING = []


def queue_for_approval(refund, approver):
    """Hold a refund until the approver signs it off."""
    PENDING.append({"refund": refund, "approver": approver})
