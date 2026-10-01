"""The shop's API: one Flask app. The view modules register its routes."""
from flask import Flask, jsonify

import config

app = Flask(__name__)


@app.get("/api/config")
def get_config():
    """What the frontend shows: the approval threshold, so the refund form warns at the right amount."""
    return jsonify({"approval_threshold_gbp": config.APPROVAL_THRESHOLD_GBP})
