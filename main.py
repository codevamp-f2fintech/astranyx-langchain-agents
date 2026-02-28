import time
import threading
from resume_indexing_agent import resume_indexing_agent
from job_description_agent import jd_matching_agent  # This calls your parameterless function

print("🚀 ATS Agents Started")

def run_agents():

    while True:

        print("\n===== Resume Agent Running =====")
        resume_indexing_agent()

        print("\n===== JD Matching Agent Running =====")
        jd_matching_agent()  # This correctly calls the function with no parameters

        print("\nSleeping 10 minutes...\n")

        time.sleep(600)


# Run agents in background thread
threading.Thread(target=run_agents).start()


# Simple web server to keep Render alive
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ATS Agents Running")


port = 10000
server = HTTPServer(("", port), Handler)

print("🌐 Web Service Running on port", port)

server.serve_forever()