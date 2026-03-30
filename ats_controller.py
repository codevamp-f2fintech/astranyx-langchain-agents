# ats_controller.py
import asyncio
import time
import os
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from nats_publisher import NATSPublisher
from datetime import datetime
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("🚀 ATS NATS Controller Starting...")
print("=" * 60)
print("⚡ INSTANT PROCESSING ENABLED (MongoDB Change Streams)")
print("   New resumes in MongoDB will trigger immediate processing")
print("=" * 60)

MONGO_URI = os.getenv("MONGODB_URI")
NATS_SERVERS = os.getenv("NATS_SERVERS", "nats://localhost:4222")


class MongoDBWatcher:
    """Watch MongoDB for new resumes and trigger processing"""
    
    def __init__(self, publisher):
        self.publisher = publisher
        self.mongo = None
        self.running = True
        self.last_check = None
        
    async def connect(self):
        """Connect to MongoDB"""
        try:
            self.mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            self.mongo.admin.command('ping')
            self.db = self.mongo["ats"]
            self.collection = self.db["applications"]
            logger.info("✅ MongoDB Watcher connected")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            return False
    
    async def watch_with_change_stream(self):
        """Watch using MongoDB change streams (instant)"""
        try:
            # Check if replica set is enabled
            result = self.mongo.admin.command('replSetGetStatus')
            logger.info("✅ MongoDB replica set detected - using change streams")
            
            pipeline = [{'$match': {'operationType': 'insert'}}]
            
            with self.collection.watch(pipeline) as stream:
                for change in stream:
                    if not self.running:
                        break
                    
                    document = change['fullDocument']
                    application_id = str(document.get('_id'))
                    
                    if document.get('resume'):
                        logger.info(f"⚡ INSTANT: New resume detected in MongoDB: {application_id}")
                        await self.publisher.publish_resume_new(application_id)
                        
        except OperationFailure as e:
            logger.warning(f"Change stream not available: {e}")
            logger.warning("Falling back to polling mode...")
            await self.watch_with_polling()
        except Exception as e:
            logger.error(f"Unexpected error in change stream: {e}")
    
    async def watch_with_polling(self):
        """Fallback: Poll MongoDB every 5 seconds"""
        logger.info("🔄 Using polling mode (checks every 5 seconds)")
        self.last_check = datetime.now()
        
        while self.running:
            try:
                new_resumes = self.collection.find({
                    "resume": {"$exists": True, "$ne": None},
                    "createdAt": {"$gt": self.last_check}
                })
                
                for doc in new_resumes:
                    application_id = str(doc.get('_id'))
                    logger.info(f"⚡ POLLING: New resume found: {application_id}")
                    await self.publisher.publish_resume_new(application_id)
                
                self.last_check = datetime.now()
                
            except Exception as e:
                logger.error(f"Polling error: {e}")
            
            await asyncio.sleep(5)
    
    async def run(self):
        """Start watching MongoDB"""
        if not await self.connect():
            logger.error("Cannot start MongoDB watcher")
            return
        await self.watch_with_change_stream()
    
    def stop(self):
        """Stop the watcher"""
        self.running = False
        if self.mongo:
            self.mongo.close()


class ATSController:
    def __init__(self, servers="nats://localhost:4222"):
        self.servers = servers
        self.loop = asyncio.new_event_loop()
        self.publisher = NATSPublisher(servers)
        self.mongo_watcher = None
        self.resume_agent_task = None
        self.jd_agent_task = None

    def start(self):
        """Start event loop and agents"""
        loop_thread = Thread(target=self._run_loop, daemon=True)
        loop_thread.start()
        print("✅ Controller event loop started")

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    async def _main(self):
        # Connect to NATS
        await self.publisher.connect()
        print("✅ Controller connected to NATS")
        
        # Start MongoDB watcher
        self.mongo_watcher = MongoDBWatcher(self.publisher)
        asyncio.create_task(self.mongo_watcher.run())
        print("✅ MongoDB Watcher started - listening for new resumes")
        
        # Start the agents
        from resume_indexing_agent import run_resume_agent
        from job_description_agent import run_jd_agent
        
        self.resume_agent_task = asyncio.create_task(run_resume_agent())
        self.jd_agent_task = asyncio.create_task(run_jd_agent())
        
        print("✅ Resume Agent started")
        print("✅ JD Agent started")
        
        print("\n" + "="*60)
        print("🎯 SYSTEM READY - Instant processing enabled!")
        print("   New resumes added to MongoDB will be processed immediately")
        print("="*60 + "\n")
        
        # Keep running
        await asyncio.Event().wait()


def main():
    controller = ATSController()
    controller.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")

if __name__ == "__main__":
    main()