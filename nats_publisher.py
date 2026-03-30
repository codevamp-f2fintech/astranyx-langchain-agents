# nats_publisher.py
import asyncio
import json
import nats
from datetime import datetime
from typing import Optional
from pymongo import MongoClient
from bson import ObjectId
import os
from dotenv import load_dotenv

load_dotenv()


class NATSPublisher:
    def __init__(self, servers="nats://localhost:4222"):
        self.servers = servers
        self.nc: Optional[nats.NATS] = None
        self.mongo = MongoClient(os.getenv("MONGODB_URI"))
        self.db = self.mongo["ats"]
        self.applications = self.db["applications"]

    async def connect(self):
        try:
            self.nc = await nats.connect(self.servers)
            print(f"✅ Connected to NATS at {self.servers}")
        except Exception as e:
            print(f"❌ Failed to connect to NATS: {e}")
            raise

    async def close(self):
        if self.nc:
            await self.nc.close()
        if self.mongo:
            self.mongo.close()

    async def publish_resume_new(self, application_id: str):
        """Publish when a new resume is uploaded"""
        if not self.nc:
            raise Exception("NATS not connected")
        
        message = {
            "application_id": application_id,
            "timestamp": datetime.now().isoformat(),
        }
        await self.nc.publish("resume.new", json.dumps(message).encode())
        print(f"📤 Published resume.new for {application_id}")

    async def publish_resume_batch(self):
        """Publish to process pending resumes"""
        if not self.nc:
            raise Exception("NATS not connected")
        
        message = {"timestamp": datetime.now().isoformat()}
        await self.nc.publish("resume.batch.process", json.dumps(message).encode())
        print("📤 Published resume.batch.process")

    async def publish_jd_match_job(self, job_id: str):
        """Publish to match resumes for a specific job"""
        if not self.nc:
            raise Exception("NATS not connected")
        
        message = {
            "job_id": job_id,
            "timestamp": datetime.now().isoformat(),
        }
        await self.nc.publish("jd.match.job", json.dumps(message).encode())
        print(f"📤 Published jd.match.job for {job_id}")

    async def publish_jd_match_company(self, company_id: str):
        """Publish to match resumes for all jobs in a company"""
        if not self.nc:
            raise Exception("NATS not connected")
        
        message = {
            "company_id": company_id,
            "timestamp": datetime.now().isoformat(),
        }
        await self.nc.publish("jd.match.company", json.dumps(message).encode())
        print(f"📤 Published jd.match.company for {company_id}")

    async def publish_jd_match_all(self):
        """Publish to match resumes for all companies"""
        if not self.nc:
            raise Exception("NATS not connected")
        
        message = {"timestamp": datetime.now().isoformat()}
        await self.nc.publish("jd.match.all", json.dumps(message).encode())
        print("📤 Published jd.match.all")
    
    async def check_and_publish_pending(self):
        """Check for pending resumes and publish them"""
        pending_resumes = self.applications.find({
            "resume": {"$exists": True},
            "$or": [
                {"rag_uploaded": False},
                {"rag_uploaded": {"$exists": False}}
            ]
        }).limit(10)
        
        pending_count = 0
        for app in pending_resumes:
            await self.publish_resume_new(str(app["_id"]))
            pending_count += 1
        
        if pending_count > 0:
            print(f"📤 Published {pending_count} pending resumes")
        
        return pending_count