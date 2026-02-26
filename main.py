#!/usr/bin/env python3
"""
Astranyx LangChain Agents - Production Version (Render Ready)
"""

import os
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import time
from dotenv import load_dotenv

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# =========================
# HEALTH CHECK SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


def start_health_server():

    port = int(os.environ.get("PORT", 10000))

    server = HTTPServer(("0.0.0.0", port), HealthHandler)

    logger.info(f"Health Server Running On Port {port}")

    server.serve_forever()


# =========================
# IMPORT AGENTS
# =========================

try:
    from resume_indexing_agent import run_resume_indexing_agent
    logger.info("Resume Agent Loaded")
except Exception as e:
    logger.error(f"Resume Agent Error: {e}")
    run_resume_indexing_agent = None


try:
    from job_description_agent import run_job_description_agent
    logger.info("Job Agent Loaded")
except Exception as e:
    logger.error(f"Job Agent Error: {e}")
    run_job_description_agent = None


# =========================
# RUN AGENTS
# =========================

def run_agents():

    if run_resume_indexing_agent:
        logger.info("Starting Resume Agent")
        run_resume_indexing_agent()

    if run_job_description_agent:
        logger.info("Starting Job Agent")
        run_job_description_agent()


# =========================
# MAIN
# =========================

def main():

    logger.info("Starting Astranyx Agents")

    load_dotenv()

    run_agents()

    # Keep server alive
    while True:
        time.sleep(60)


# =========================
# ENTRY
# =========================

if __name__ == "__main__":

    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True
    )

    health_thread.start()

    main()