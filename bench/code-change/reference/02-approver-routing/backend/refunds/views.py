"""The refunds endpoint."""
from flask import jsonify, request

from app import app
from approvals import queue_for_approval
from .rules import approver_for, validate


@app.post("/api/refunds")
def create_refund():
    """Refund at once, or queue the refund for approval when it is large."""
    refund = request.get_json()
    validate(refund)
    approver = approver_for(refund["amount"])
    if approver:
        queue_for_approval(refund, approver)
        return jsonify({"status": "awaiting approval", "approver": approver}), 202
    return jsonify({"status": "refunded"}), 201
