#!/usr/bin/env python3
"""
Main entry point for Astranyx LangChain Agents
Handles resume indexing and job description processing
"""

import os
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# ============================================
# HEALTH CHECK SERVER (for Render port binding)
# ============================================

class HealthCheckHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        self.wfile.write(b'OK')
        self.wfile.write(f'\nService: Astranyx LangChain Agents'.encode())
        self.wfile.write(f'\nTime: {time.time()}'.encode())


    def do_HEAD(self):

        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()


    def log_message(self, format, *args):

        return


def run_health_server():

    port = int(os.environ.get('PORT', 10000))
    host = '0.0.0.0'

    try:

        server = HTTPServer((host, port), HealthCheckHandler)

        logger.info(f"✅ Health check server running on {host}:{port}")

        server.serve_forever()

    except Exception as e:

        logger.error(f"❌ Failed to start health server: {e}")


# ============================================
# AGENT IMPORTS
# ============================================

try:
    from resume_indexing_agent import run_resume_indexing_agent
    logger.info("✅ Successfully imported resume_indexing_agent")
    resume_indexing_available = True

except ImportError as e:

    logger.error(f"❌ Failed to import resume_indexing_agent: {e}")
    resume_indexing_available = False
    run_resume_indexing_agent = None



try:
    from job_description_agent import run_job_description_agent
    logger.info("✅ Successfully imported job_description_agent")
    job_description_available = True

except ImportError as e:

    logger.error(f"❌ Failed to import job_description_agent: {e}")
    job_description_available = False
    run_job_description_agent = None



from dotenv import load_dotenv



# ============================================
# AGENT FUNCTIONS
# ============================================

def run_resume_indexing():

    if not resume_indexing_available:
        logger.error("❌ Cannot run resume_indexing_agent")
        return

    try:

        logger.info("📄 Starting Resume Indexing Agent...")

        run_resume_indexing_agent()

        logger.info("✅ Resume Indexing Completed")

    except Exception as e:

        logger.error(f"❌ Resume Agent Error: {e}")



def run_job_description():

    if not job_description_available:
        logger.error("❌ Cannot run job_description_agent")
        return

    try:

        logger.info("🎯 Starting JD Matching Agent...")

        run_job_description_agent()

        logger.info("✅ JD Matching Completed")

    except Exception as e:

        logger.error(f"❌ JD Agent Error: {e}")



def run_both_agents():

    run_resume_indexing()

    run_job_description()



# ============================================
# MAIN
# ============================================

def main():

    logger.info("🚀 Starting Astranyx LangChain Agents")

    load_dotenv()

    agent_to_run = os.getenv('AGENT_TO_RUN', 'both').lower()

    logger.info(f"🎯 Agent to run: {agent_to_run}")


    if agent_to_run == 'resume':

        run_resume_indexing()


    elif agent_to_run == 'job':

        run_job_description()


    elif agent_to_run == 'both':

        run_both_agents()


    elif agent_to_run == 'periodic':

        while True:

            logger.info("⏰ Running periodic agents")

            run_both_agents()

            time.sleep(3600)


    else:

        logger.error("❌ Invalid AGENT_TO_RUN value")


    while True:

        time.sleep(60)



# ============================================
# ENTRY POINT
# ============================================

if __name__ == "__main__":

    logger.info("=" * 50)
    logger.info("ASTRANYX AGENTS STARTING")
    logger.info("=" * 50)


    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True
    )

    health_thread.start()

    logger.info("✅ Health server started")


    main()