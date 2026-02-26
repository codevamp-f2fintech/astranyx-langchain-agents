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
    """Simple health check endpoint for Render"""
    
    def do_GET(self):
        """Handle GET requests - always return OK status"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(b'OK')
        self.wfile.write(f'\nService: Astranyx LangChain Agents'.encode())
        self.wfile.write(f'\nTime: {time.time()}'.encode())
    
    def do_HEAD(self):
        """Handle HEAD requests - same as GET but no body"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default HTTP server logs"""
        # Only log errors, not every request
        if args[1] != 200:
            logger.info(f"Health check: {args[0]} {args[1]} {args[2]}")
        return

def run_health_server():
    """
    Run a simple HTTP server for Render health checks
    This binds to the PORT environment variable required by Render
    """
    port = int(os.environ.get('PORT', 10000))
    host = '0.0.0.0'  # Required for Render
    
    try:
        server = HTTPServer((host, port), HealthCheckHandler)
        logger.info(f"✅ Health check server running on {host}:{port}")
        logger.info(f"📡 This satisfies Render's port binding requirement")
        server.serve_forever()
    except Exception as e:
        logger.error(f"❌ Failed to start health server: {e}")
        # Don't exit - the main app might still work
        logger.warning("⚠️ Continuing without health server - Render may timeout")

# ============================================
# YOUR AGENT IMPORTS
# ============================================

# Import your agent modules
try:
    from resume_indexing_agent import run_resume_indexing_agent
    logger.info("✅ Successfully imported resume_indexing_agent")
    resume_indexing_available = True
except ImportError as e:
    logger.error(f"❌ Failed to import resume_indexing_agent: {e}")
    logger.error("Make sure resume_indexing_agent.py exists in the same directory")
    resume_indexing_available = False
    run_resume_indexing_agent = None

try:
    from job_description_agent import run_job_description_agent
    logger.info("✅ Successfully imported job_description_agent")
    job_description_available = True
except ImportError as e:
    logger.error(f"❌ Failed to import job_description_agent: {e}")
    logger.error("Make sure job_description_agent.py exists in the same directory")
    job_description_available = False
    run_job_description_agent = None

# Import other dependencies you might need
import sys
from dotenv import load_dotenv

# ============================================
# MAIN APPLICATION LOGIC
# ============================================

def run_resume_indexing():
    """Wrapper function to run resume indexing agent"""
    if not resume_indexing_available or not run_resume_indexing_agent:
        logger.error("❌ Cannot run resume_indexing_agent - import failed")
        return None
    
    try:
        logger.info("📄 Starting Resume Indexing Agent...")
        # Add any parameters your agent needs
        # result = run_resume_indexing_agent(param1, param2)
        result = run_resume_indexing_agent()
        logger.info(f"✅ Resume Indexing Agent completed successfully")
        return result
    except Exception as e:
        logger.error(f"❌ Error in Resume Indexing Agent: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_job_description():
    """Wrapper function to run job description agent"""
    if not job_description_available or not run_job_description_agent:
        logger.error("❌ Cannot run job_description_agent - import failed")
        return None
    
    try:
        logger.info("💼 Starting Job Description Agent...")
        # Add any parameters your agent needs
        # result = run_job_description_agent(param1, param2)
        result = run_job_description_agent()
        logger.info(f"✅ Job Description Agent completed successfully")
        return result
    except Exception as e:
        logger.error(f"❌ Error in Job Description Agent: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_both_agents():
    """Run both agents sequentially"""
    logger.info("🔄 Running both agents...")
    
    results = {}
    
    # Run resume indexing agent
    resume_result = run_resume_indexing()
    if resume_result:
        results['resume_indexing'] = resume_result
    
    # Run job description agent
    job_result = run_job_description()
    if job_result:
        results['job_description'] = job_result
    
    return results

def main():
    """Main function to run your agents based on environment configuration"""
    logger.info("🚀 Starting Astranyx LangChain Agents")
    logger.info(f"📊 Available agents: Resume Indexing={resume_indexing_available}, Job Description={job_description_available}")
    
    # Load environment variables
    load_dotenv()
    logger.info("✅ Environment variables loaded")
    
    # Check for required API keys (customize this list)
    required_vars = ['OPENAI_API_KEY']  # Add your required keys
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.warning(f"⚠️ Missing environment variables: {', '.join(missing_vars)}")
        logger.warning("Some functionality may be limited")
    
    # Determine which agents to run based on environment variable
    # You can set AGENT_TO_RUN in Render environment variables
    agent_to_run = os.getenv('AGENT_TO_RUN', 'both').lower()
    logger.info(f"🎯 Agent to run: {agent_to_run}")
    
    if agent_to_run == 'resume' or agent_to_run == 'resume_indexing':
        # Run only resume indexing agent
        run_resume_indexing()
        
    elif agent_to_run == 'job' or agent_to_run == 'job_description':
        # Run only job description agent
        run_job_description()
        
    elif agent_to_run == 'both':
        # Run both agents
        run_both_agents()
        
    elif agent_to_run == 'sequential':
        # Run in sequence with custom logic
        logger.info("🔄 Running agents in sequential mode")
        
        # Example: Run resume indexing first, then wait, then job description
        run_resume_indexing()
        logger.info("⏳ Waiting 5 seconds before running job description...")
        time.sleep(5)
        run_job_description()
        
    elif agent_to_run == 'periodic':
        # Run agents periodically (example: every hour)
        logger.info("⏰ Running agents in periodic mode")
        
        while True:
            logger.info(f"🕐 Starting periodic run at {time.ctime()}")
            
            # Run both agents
            run_both_agents()
            
            # Wait for specified interval (default 1 hour)
            interval = int(os.getenv('RUN_INTERVAL', 3600))
            logger.info(f"⏳ Sleeping for {interval} seconds until next run...")
            time.sleep(interval)
    
    else:
        logger.error(f"❌ Unknown AGENT_TO_RUN value: {agent_to_run}")
        logger.info("Valid values: 'resume', 'job', 'both', 'sequential', 'periodic'")
    
    logger.info("👋 Agent execution completed. Main thread will stay alive for health checks.")
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(60)  # Sleep for 60 seconds
            # Log heartbeat every 5 minutes
            if int(time.time()) % 300 < 60:  # Roughly every 5 minutes
                logger.debug("💓 Heartbeat: main thread still running")
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down gracefully...")

# ============================================
# ENTRY POINT
# ============================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("ASTRANYX LANGCHAIN AGENTS - Resume & Job Description Processing")
    logger.info("=" * 60)
    
    # Start health check server in background thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    logger.info("✅ Health check thread started")
    
    # Run main application
    main()