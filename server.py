"""
Flask wrapper for resume_agent — deploy as a free Web Service on Render.

Endpoints:
    GET  /health     → health check (keeps Render from sleeping)
    POST /run-agent  → triggers the agent in a background thread
    GET  /status     → check if the agent is currently running
"""

import threading
import time
from flask import Flask, jsonify, request

# Import everything from resume_agent (clients, model, agent functions)
    resume_indexing_agent,
    jd_matching_agent,
    init_resources,
    AGENT,
)

app = Flask(__name__)

# Agent state tracking
_agent_lock = threading.Lock()
_agent_running = False
_last_run = None
_last_error = None


def _run_agent_task(agent_mode: str):
    """Run the agent in a background thread."""
    global _agent_running, _last_run, _last_error
    try:
        if agent_mode in ("index", "both"):
            resume_indexing_agent()
        if agent_mode in ("matching", "both"):
            jd_matching_agent()
        _last_error = None
        print("🎯 Agent finished successfully")
    except Exception as e:
        _last_error = str(e)
        print(f"❌ Agent error: {e}")
    finally:
        _last_run = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        with _agent_lock:
            global _agent_running
            _agent_running = False


@app.route("/health", methods=["GET"])
def health():
    """Health check — Render pings this to know the service is alive."""
    return jsonify({"status": "ok", "agent_configured": AGENT}), 200


@app.route("/run-agent", methods=["POST", "GET"])
def run_agent():
    """Trigger the agent. Accepts optional ?agent=index|matching|both query param."""
    global _agent_running

    with _agent_lock:
        if _agent_running:
            return jsonify({"message": "Agent is already running"}), 409
        _agent_running = True

    agent_mode = request.args.get("agent", AGENT)
    if agent_mode not in ("index", "matching", "both"):
        with _agent_lock:
            _agent_running = False
        return jsonify({"error": f"Invalid agent mode: {agent_mode}"}), 400

    thread = threading.Thread(target=_run_agent_task, args=(agent_mode,), daemon=True)
    thread.start()

    return jsonify({
        "message": "Agent started",
        "agent": agent_mode,
    }), 202


@app.route("/status", methods=["GET"])
def status():
    """Check agent status."""
    return jsonify({
        "running": _agent_running,
        "last_run": _last_run,
        "last_error": _last_error,
        "agent_mode": AGENT,
    }), 200


if __name__ == "__main__":
    # Local dev only — on Render, gunicorn runs this
    app.run(host="0.0.0.0", port=10000, debug=True)
