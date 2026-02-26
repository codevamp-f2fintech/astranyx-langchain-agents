#!/usr/bin/env python3
"""
Main entry point for Astranyx LangChain Agents
This file runs the resume agent and includes a health check server for Render
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
# YOUR EXISTING IMPORTS
# ============================================

# Import your existing modules
try:
    from resume_agent import run_resume_agent
    logger.info("✅ Successfully imported resume_agent")
except ImportError as e:
    logger.error(f"❌ Failed to import resume_agent: {e}")
    logger.error("Make sure resume_agent.py exists in the same directory")
    run_resume_agent = None  # Set to None so we can handle gracefully

# Import other dependencies you might need
import sys
from dotenv import load_dotenv

# ============================================
# YOUR EXISTING CODE
# ============================================

def main():
    """Main function to run your agent"""
    logger.info("🚀 Starting Astranyx LangChain Agents")
    
    # Load environment variables
    load_dotenv()
    logger.info("✅ Environment variables loaded")
    
    # Check for required API keys
    required_vars = ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY']  # Add your required keys
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.warning(f"⚠️ Missing environment variables: {', '.join(missing_vars)}")
        logger.warning("Some functionality may be limited")
    
    # Run your agent
    if run_resume_agent:
        try:
            logger.info("🤖 Executing run_resume_agent...")
            
            # If your agent takes parameters, add them here
            # result = run_resume_agent(your_params)
            
            # For now, just call it without params
            result = run_resume_agent()
            
            logger.info(f"✅ Agent execution completed: {result}")
            
        except Exception as e:
            logger.error(f"❌ Error running resume_agent: {e}")
            import traceback
            traceback.print_exc()
    else:
        logger.error("❌ Cannot run agent - import failed")
    
    # Keep the main thread alive
    logger.info("👂 Agent execution completed. Main thread will stay alive for health checks.")
    
    # If you need the agent to run continuously, add a loop here
    # For periodic tasks, you can use:
    """
    while True:
        try:
            # Run your agent periodically
            run_resume_agent()
            # Wait before next execution
            time.sleep(3600)  # Sleep for 1 hour
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(60)  # Wait before retry
    """
    
    # Instead of a busy loop, we can just keep the main thread alive
    # while waiting for the health server thread
    try:
        # This will keep the main thread alive indefinitely
        # The health server thread runs in the background
        while True:
            time.sleep(60)  # Sleep for 60 seconds
            # Optionally log that we're still alive
            logger.debug("Heartbeat: main thread still running")
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")

# ============================================
# ENTRY POINT
# ============================================

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("ASTRANYX LANGCHAIN AGENTS")
    logger.info("=" * 50)
    
    # Start health check server in background thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    logger.info("✅ Health check thread started")
    
    # Run main application
    main()