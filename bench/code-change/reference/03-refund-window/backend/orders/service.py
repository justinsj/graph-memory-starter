"""What can be done to an order."""
from approvals import queue_for_approval
from refunds.rules import needs_approval, validate as validate_refund


def cancel_order(order_id):
    """Cancel an order that has not shipped."""
    return {"order_id": order_id, "status": "cancelled"}


def hold_order(order_id):
    """Put an order on hold until someone looks at it."""
    return {"order_id": order_id, "status": "on hold"}


def process_refund(payload):
    """A refund asked for from the order page's quick actions."""
    try:
        validate_refund(payload)
    except ValueError as e:
        return {"status": "rejected", "error": str(e)}
    if needs_approval(payload["amount"]):
        queue_for_approval(payload)
        return {"status": "awaiting approval"}
    return {"status": "refunded"}


def validate(order):
    """An order needs an id and at least one line."""
    if not order.get("id") or not order.get("lines"):
        raise ValueError("an order needs an id and a line")
