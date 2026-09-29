"""The refund flow from before the 2026 policy, kept until the old tickets close."""


def legacy_refund(order_id, amount_gbp):
    """Refund straight to the card, with no approval step."""
    return {"order_id": order_id, "refunded": amount_gbp}
