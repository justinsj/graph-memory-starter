"""The refunds endpoint."""
from flask import jsonify, request

from app import app
from approvals import queue_for_approval
from .rules import needs_approval, validate


@app.post("/api/refunds")
def create_refund():
    """Refund at once, or queue the refund for approval when it is large."""
    refund = request.get_json()
    validate(refund)
    if needs_approval(refund["amount"]):
        queue_for_approval(refund)
        return jsonify({"status": "awaiting approval"}), 202
    return jsonify({"status": "refunded"}), 201
