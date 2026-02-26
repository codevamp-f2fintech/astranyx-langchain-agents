import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ===============================
# HEALTH SERVER (REQUIRED)
# ===============================

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ATS Agents Running")

    def log_message(self, format, *args):
        return


def start_server():

    port = int(os.environ.get("PORT", 10000))

    server = HTTPServer(("0.0.0.0", port), Handler)

    print("Server started on port", port)

    server.serve_forever()


# ===============================
# IMPORT AGENTS
# ===============================

try:
    from resume_indexing_agent import run_resume_indexing_agent
    print("Resume agent loaded")
except:
    run_resume_indexing_agent = None
    print("Resume agent missing")

try:
    from job_description_agent import run_job_description_agent
    print("JD agent loaded")
except:
    run_job_description_agent = None
    print("JD agent missing")


# ===============================
# RUN AGENTS
# ===============================

def run_agents():

    print("Starting Agents")

    if run_resume_indexing_agent:
        run_resume_indexing_agent()

    if run_job_description_agent:
        run_job_description_agent()

    print("Agents Finished")


# ===============================
# START
# ===============================

if __name__ == "__main__":

    # Start server FIRST (important)
    threading.Thread(target=start_server).start()

    # Small delay so Render detects port
    time.sleep(3)

    # Run agents
    run_agents()

    # Keep alive
    while True:
        time.sleep(60)