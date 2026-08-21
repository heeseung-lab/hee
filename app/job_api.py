import hmac
import os
from flask import jsonify, request

from app.job_runner import get_state, start_collection


def register_job_routes(app):
    @app.post("/api/run-all")
    def run_all_api():
        expected = os.getenv("JOB_TOKEN", "")
        supplied = request.headers.get("Authorization", "")
        if not expected or not hmac.compare_digest(supplied, f"Bearer {expected}"):
            return jsonify(error="unauthorized"), 401
        if not start_collection():
            return jsonify(ok=True, started=False, reason="already_running", state=get_state()), 202
        return jsonify(ok=True, started=True, state=get_state()), 202

    @app.get("/api/run-state")
    def run_state_api():
        return jsonify(get_state())
