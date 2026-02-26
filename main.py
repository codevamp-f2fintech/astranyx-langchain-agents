#!/usr/bin/env python3
"""
Main entry point for Astranyx LangChain Agents
Handles resume indexing and job description processing
"""

import os
import sys
import time
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

# ============================================
# CONFIGURATION
# ============================================

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log')
    ]
)

logger = logging.getLogger(__name__)

# ============================================
# HEALTH CHECK SERVER (for Render port binding)
# ============================================

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple health check endpoint for Render"""
    
    def do_GET(self):
        """Handle GET requests - return service status"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        
        self.wfile.write(b'OK')
        self.wfile.write(f'\nService: Astranyx LangChain Agents'.encode())
        self.wfile.write(f'\nStatus: Running'.encode())
        self.wfile.write(f'\nTime: {time.time()}'.encode())
        self.wfile.write(f'\nAgents: Resume Indexing, Job Description'.encode())

    def do_HEAD(self):
        """Handle HEAD requests - just return headers"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

    def log_message(self, format, *args):
        """Suppress default HTTP server logs to keep console clean"""
        # Only log non-200 responses
        if args[1] != '200':
            logger.info(f"Health check: {args[0]} {args[1]} {args[2]}")
        return


def run_health_server():
    """Run health check server in background thread"""
    port = int(os.environ.get('PORT', 10000))
    host = '0.0.0.0'
    
    try:
        server = HTTPServer((host, port), HealthCheckHandler)
        logger.info(f"✅ Health check server running on {host}:{port}")
        logger.info(f"📡 Service will stay alive on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"❌ Failed to start health server: {e}")
        logger.warning("⚠️ Continuing without health server - Render may timeout")


# ============================================
# AGENT IMPORTS
# ============================================

# Try importing resume indexing agent
try:
    from resume_indexing_agent import run_resume_indexing_agent
    logger.info("✅ Successfully imported resume_indexing_agent")
    resume_indexing_available = True
except ImportError as e:
    logger.error(f"❌ Failed to import resume_indexing_agent: {e}")
    logger.error("📁 Make sure resume_indexing_agent.py exists in the same directory")
    resume_indexing_available = False
    run_resume_indexing_agent = None

# Try importing job description agent
try:
    from job_description_agent import run_job_description_agent
    logger.info("✅ Successfully imported job_description_agent")
    job_description_available = True
except ImportError as e:
    logger.error(f"❌ Failed to import job_description_agent: {e}")
    logger.error("📁 Make sure job_description_agent.py exists in the same directory")
    job_description_available = False
    run_job_description_agent = None


# ============================================
# ENVIRONMENT VALIDATION
# ============================================

def check_environment():
    """Check if all required environment variables are set"""
    logger.info("🔍 Checking environment configuration...")
    
    # Load .env file if it exists (for local development)
    load_dotenv()
    
    # Track missing variables
    missing_vars = []
    
    # Check for common service variables (uncomment as needed)
    # if os.getenv('MONGODB_URI') is None:
    #     missing_vars.append('MONGODB_URI')
    # if os.getenv('QDRANT_URL') is None:
    #     missing_vars.append('QDRANT_URL')
    # if os.getenv('QDRANT_API_KEY') is None:
    #     missing_vars.append('QDRANT_API_KEY')
    # if os.getenv('AWS_ACCESS_KEY_ID') is None:
    #     missing_vars.append('AWS_ACCESS_KEY_ID')
    # if os.getenv('AWS_SECRET_ACCESS_KEY') is None:
    #     missing_vars.append('AWS_SECRET_ACCESS_KEY')
    
    if missing_vars:
        logger.warning(f"⚠️ Missing environment variables: {', '.join(missing_vars)}")
        logger.warning("Some functionality may be limited")
        return False
    
    logger.info("✅ Environment check passed")
    return True


# ============================================
# AGENT EXECUTION FUNCTIONS
# ============================================

def run_resume_indexing():
    """Execute resume indexing agent with error handling"""
    if not resume_indexing_available:
        logger.error("❌ Cannot run resume_indexing_agent - import failed")
        return False
    
    try:
        logger.info("📄 " + "="*40)
        logger.info("📄 Starting Resume Indexing Agent...")
        logger.info("📄 " + "="*40)
        
        # Execute the agent
        start_time = time.time()
        result = run_resume_indexing_agent()
        elapsed_time = time.time() - start_time
        
        logger.info(f"✅ Resume Indexing Completed in {elapsed_time:.2f} seconds")
        logger.info(f"📊 Result: {result}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Resume Agent Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_job_description():
    """Execute job description agent with error handling"""
    if not job_description_available:
        logger.error("❌ Cannot run job_description_agent - import failed")
        return False
    
    try:
        logger.info("🎯 " + "="*40)
        logger.info("🎯 Starting Job Description Matching Agent...")
        logger.info("🎯 " + "="*40)
        
        # Execute the agent
        start_time = time.time()
        result = run_job_description_agent()
        elapsed_time = time.time() - start_time
        
        logger.info(f"✅ JD Matching Completed in {elapsed_time:.2f} seconds")
        logger.info(f"📊 Result: {result}")
        return True
        
    except Exception as e:
        logger.error(f"❌ JD Agent Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_both_agents():
    """Run both agents sequentially"""
    logger.info("🔄 " + "="*40)
    logger.info("🔄 Running Both Agents")
    logger.info("🔄 " + "="*40)
    
    results = {
        'resume_indexing': run_resume_indexing(),
        'job_description': run_job_description()
    }
    
    # Summary
    logger.info("📊 " + "="*40)
    logger.info("📊 EXECUTION SUMMARY")
    logger.info("📊 " + "="*40)
    for agent, success in results.items():
        status = "✅ Success" if success else "❌ Failed"
        logger.info(f"{agent}: {status}")
    
    return all(results.values())


# ============================================
# MAIN APPLICATION
# ============================================

def main():
    """Main function to run agents based on configuration"""
    logger.info("🚀 " + "="*50)
    logger.info("🚀 ASTRANYX LANGCHAIN AGENTS")
    logger.info("🚀 " + "="*50)
    
    # Check environment
    check_environment()
    
    # Get agent to run from environment variable
    agent_to_run = os.getenv('AGENT_TO_RUN', 'both').lower()
    run_interval = int(os.getenv('RUN_INTERVAL', '3600'))  # Default: 1 hour
    
    logger.info(f"🎯 Configuration:")
    logger.info(f"   - Agent to run: {agent_to_run}")
    logger.info(f"   - Run interval: {run_interval}s")
    logger.info(f"   - Resume agent available: {resume_indexing_available}")
    logger.info(f"   - JD agent available: {job_description_available}")
    
    # Execute based on configuration
    if agent_to_run == 'resume':
        run_resume_indexing()
        
    elif agent_to_run == 'job':
        run_job_description()
        
    elif agent_to_run == 'both':
        run_both_agents()
        
    elif agent_to_run == 'periodic':
        logger.info("⏰ Running in periodic mode - will execute every {} seconds".format(run_interval))
        cycle_count = 0
        
        while True:
            cycle_count += 1
            logger.info(f"🔄 " + "="*40)
            logger.info(f"🔄 PERIODIC RUN #{cycle_count} - {time.ctime()}")
            logger.info(f"🔄 " + "="*40)
            
            # Run both agents
            run_both_agents()
            
            # Wait for next interval
            logger.info(f"⏳ Sleeping for {run_interval} seconds until next run...")
            logger.info(f"📅 Next run at: {time.ctime(time.time() + run_interval)}")
            logger.info("-" * 50)
            time.sleep(run_interval)
    
    elif agent_to_run == 'once':
        # Run once and exit (for debugging)
        logger.info("🎯 Running once and exiting")
        run_both_agents()
        logger.info("✅ Execution complete. Exiting.")
        return
        
    else:
        logger.error(f"❌ Invalid AGENT_TO_RUN value: '{agent_to_run}'")
        logger.info("Valid values: 'resume', 'job', 'both', 'periodic', 'once'")
    
    # Keep main thread alive for health checks
    logger.info("👂 Main thread will stay alive for health checks")
    logger.info("💓 Heartbeat every 60 seconds")
    
    try:
        while True:
            time.sleep(60)
            # Log heartbeat every 5 minutes (every 5th iteration)
            if int(time.time()) % 300 < 60:
                logger.debug(f"💓 Heartbeat - Agents: R:{resume_indexing_available} JD:{job_description_available}")
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down gracefully...")
        sys.exit(0)


# ============================================
# ENTRY POINT
# ============================================

if __name__ == "__main__":
    # Print startup banner
    print("\n" + "="*60)
    print(" ASTRANYX LANGCHAIN AGENTS - Resume & Job Description Processing")
    print("="*60 + "\n")
    
    # Start health check server in background thread
    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True
    )
    health_thread.start()
    
    # Give health server a moment to start
    time.sleep(1)
    
    # Run main application
    main()