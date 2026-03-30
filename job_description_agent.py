# job_description_agent.py
import os
import asyncio
import json
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from bs4 import BeautifulSoup
import re
import nats
import logging
from datetime import datetime

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGODB_URI")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
NATS_SERVERS = os.getenv("NATS_SERVERS", "nats://localhost:4222")
QDRANT_COLLECTION = "resumes"

# Initialize services
logger.info("Initializing JD Agent services...")

try:
    mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo.admin.command('ping')
    db = mongo["ats"]
    applications = db["applications"]
    jobs = db["jobs"]
    companies = db["companies"]
    job_statuses = db["job-statuses"]
    logger.info("✅ MongoDB connected")
except Exception as e:
    logger.error(f"❌ MongoDB connection error: {e}")
    mongo = None

try:
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=60)
    qdrant.get_collections()
    logger.info("✅ Qdrant connected")
except Exception as e:
    logger.error(f"❌ Qdrant connection error: {e}")
    qdrant = None

try:
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    logger.info("✅ Sentence transformer model loaded")
except Exception as e:
    logger.error(f"❌ Model loading error: {e}")
    model = None


def clean_html(html: str) -> str:
    """Clean HTML content and return plain text"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def process_job_matching(job_id: str, nc=None):
    """Process JD matching for a specific job"""
    if qdrant is None or model is None:
        logger.error("Qdrant or Model not initialized")
        return {"selected": 0, "rejected": 0, "error": "Services not initialized"}
    
    logger.info(f"📋 Processing job matching: {job_id}")
    
    try:
        # Get job details
        job = jobs.find_one({"_id": ObjectId(job_id)})
        if not job:
            logger.error(f"Job not found: {job_id}")
            return {"selected": 0, "rejected": 0, "error": "Job not found"}
        
        job_title = job.get("title", "Unknown")
        desc = job.get("description", "")
        
        if not desc:
            logger.warning(f"Job {job_id} has no description")
            return {"selected": 0, "rejected": 0, "error": "No description"}
        
        logger.info(f"📋 Job: {job_title}")
        
        # Create vector from job description
        cleaned_desc = clean_html(desc)
        logger.info("🧠 Creating job embedding...")
        vector = model.encode(cleaned_desc).tolist()
        
        # Search in Qdrant
        logger.info("🔍 Searching Qdrant for matching resumes...")
        search_result = qdrant.query_points(
            collection_name=QDRANT_COLLECTION,
            query=vector,
            limit=10000,
            with_payload=True
        )
        
        # Extract points from search result
        results = []
        if hasattr(search_result, 'points'):
            for point in search_result.points:
                results.append({
                    "score": point.score,
                    "payload": point.payload
                })
        
        logger.info(f"📊 Found {len(results)} total results")
        
        # Filter results for this specific job
        filtered_results = []
        for r in results:
            if r["payload"] and r["payload"].get("job_id") == job_id:
                filtered_results.append(r)
        
        results = filtered_results
        logger.info(f"📊 Found {len(results)} results for this job")
        
        if not results:
            logger.info("No results found for this job")
            return {"selected": 0, "rejected": 0, "matched": False}
        
        # Calculate scores and cutoff
        scores = [r["score"] for r in results]
        best = max(scores)
        cutoff = best * 0.52
        logger.info(f"📈 Best score: {best:.4f}, Cutoff: {cutoff:.4f}")
        
        selected = 0
        rejected = 0
        
        for r in results:
            app_id = r["payload"].get("application_id")
            score = r["score"]
            
            if not app_id:
                continue
            
            status = "selected" if score >= cutoff else "rejected"
            
            if status == "selected":
                selected += 1
            else:
                rejected += 1
            
            # Update application status in MongoDB
            try:
                applications.update_one(
                    {"_id": ObjectId(app_id)},
                    {"$set": {
                        "resume_status": status,
                        "match_score": score,
                        "matched_at": datetime.now(),
                        "matched_job_id": job_id
                    }}
                )
                logger.info(f"   {app_id}: {score:.4f} - {status}")
            except Exception as e:
                logger.error(f"Error updating application {app_id}: {e}")
        
        logger.info(f"📊 Job Results - Selected: {selected}, Rejected: {rejected}")
        return {"selected": selected, "rejected": rejected, "matched": True}
        
    except Exception as e:
        logger.error(f"Error processing job {job_id}: {e}")
        return {"selected": 0, "rejected": 0, "error": str(e)}


async def run_jd_agent():
    """Run the JD agent with NATS listener"""
    logger.info("="*60)
    logger.info("🤖 JD AGENT STARTING")
    logger.info("="*60)
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Connect to NATS
            logger.info(f"Connecting to NATS at {NATS_SERVERS}...")
            nc = await nats.connect(
                NATS_SERVERS,
                reconnect_time_wait=2,
                max_reconnect_attempts=10
            )
            logger.info("✅ NATS CONNECTED")
            
            # Message handler
            async def message_handler(msg):
                logger.info(f"🔔 RECEIVED MESSAGE on {msg.subject}")
                try:
                    data = json.loads(msg.data.decode())
                    logger.info(f"📦 Message data: {data}")
                    
                    if msg.subject == "jd.match.job":
                        job_id = data.get("job_id")
                        if job_id:
                            logger.info(f"⚡ MATCHING JOB: {job_id}")
                            result = await process_job_matching(job_id, nc)
                            logger.info(f"📊 Matching result: {result}")
                        else:
                            logger.error("No job_id in message")
                            
                    elif msg.subject == "jd.match.all":
                        logger.info("⚡ MATCHING ALL JOBS REQUESTED")
                        # Add all jobs matching logic here
                        
                except Exception as e:
                    logger.error(f"Error in message handler: {e}", exc_info=True)
            
            # Subscribe to topics
            logger.info("Subscribing to jd.match.job...")
            await nc.subscribe("jd.match.job", cb=message_handler)
            
            logger.info("Subscribing to jd.match.all...")
            await nc.subscribe("jd.match.all", cb=message_handler)
            
            logger.info("✅ JD Agent subscriptions active")
            logger.info("🎧 Listening for messages on:")
            logger.info("   - jd.match.job")
            logger.info("   - jd.match.all")
            logger.info("="*60)
            logger.info("💡 Ready! Will match resumes when triggered")
            logger.info("="*60)
            
            # Keep running
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            retry_count += 1
            logger.error(f"JD Agent error (attempt {retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                logger.info(f"Retrying in 5 seconds...")
                await asyncio.sleep(5)
            else:
                logger.error("Max retries reached. Exiting.")
                raise


if __name__ == "__main__":
    try:
        asyncio.run(run_jd_agent())
    except KeyboardInterrupt:
        logger.info("\n🛑 JD Agent stopped by user")