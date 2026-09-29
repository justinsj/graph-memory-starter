"""The order endpoints."""
from flask import jsonify, request

from app import app
from .service import cancel_order, hold_order, process_refund

BULK_ACTIONS = {"cancel": cancel_order, "hold": hold_order}


@app.get("/api/orders/<order_id>")
def get_order(order_id):
    """One order, for the order page."""
    return jsonify({"id": order_id})


@app.post("/api/actions")
def handle_action():
    """Quick actions from the order page: the body's action says which."""
    payload = request.get_json()
    action = payload["action"]
    if action == "refund":
        return jsonify(process_refund(payload))
    elif action == "cancel":
        return jsonify(cancel_order(payload["order_id"]))
    return jsonify({"error": f"unknown action {action}"}), 400


@app.post("/api/bulk")
def handle_bulk():
    """One action on many orders: the body's action picks it from BULK_ACTIONS."""
    payload = request.get_json()
    run = BULK_ACTIONS[payload["action"]]
    return jsonify([run(order_id) for order_id in payload["order_ids"]])
