# resume_indexing_agent.py
import io
import os
import uuid
import asyncio
import json
import boto3
import fitz
from dotenv import load_dotenv
from pymongo import MongoClient
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer
from PIL import Image
import pytesseract
import logging
from datetime import datetime
from bson import ObjectId

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION     = os.getenv("AWS_REGION")
S3_BUCKET      = os.getenv("AWS_S3_BUCKET")
MONGO_URI      = os.getenv("MONGODB_URI")
QDRANT_URL     = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

DB_NAME           = "ats"
COLLECTION_NAME   = "applications"
QDRANT_COLLECTION = "resumes"

logger.info("Initializing Resume Agent services...")

try:
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION,
    )
    logger.info("✅ AWS S3 client initialized")
except Exception as e:
    logger.error(f"❌ Failed to initialize AWS S3: {e}")
    s3 = None

try:
    mongo        = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo.admin.command('ping')
    db           = mongo[DB_NAME]
    applications = db[COLLECTION_NAME]
    logger.info("✅ MongoDB connected")
except Exception as e:
    logger.error(f"❌ Failed to connect to MongoDB: {e}")
    mongo        = None
    applications = None

try:
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=60)
    qdrant.get_collections()
    logger.info("✅ Qdrant connected")
except Exception as e:
    logger.error(f"❌ Failed to connect to Qdrant: {e}")
    qdrant = None

try:
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    logger.info("✅ Sentence transformer model loaded")
except Exception as e:
    logger.error(f"❌ Failed to load model: {e}")
    model = None


def mongo_id_to_uuid(mongo_id):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(mongo_id)))


def extract_s3_key(url):
    return url.split(".amazonaws.com/")[-1]


def extract_text_from_s3(url):
    if not s3:
        raise Exception("AWS S3 client not initialized")

    key = extract_s3_key(url)
    logger.info(f"📥 Downloading from S3: {key}")

    obj        = s3.get_object(Bucket=S3_BUCKET, Key=key)
    file_bytes = obj["Body"].read()
    text       = ""

    if key.lower().endswith((".jpg", ".png", ".jpeg", ".gif", ".bmp")):
        try:
            image = Image.open(io.BytesIO(file_bytes))
            text  = pytesseract.image_to_string(image)
            logger.info(f"📸 OCR extracted {len(text)} chars from image")
        except Exception as e:
            logger.error(f"OCR failed for {key}: {e}")
            raise
    else:
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                logger.info(f"📄 Processing PDF with {len(doc)} pages")
                for page_num, page in enumerate(doc):
                    page_text = page.get_text()
                    if page_text:
                        text += page_text
                    else:
                        logger.info(f"Page {page_num + 1} has no text, trying OCR")
                        pix      = page.get_pixmap()
                        img_data = pix.tobytes("png")
                        img      = Image.open(io.BytesIO(img_data))
                        text    += pytesseract.image_to_string(img)
            logger.info(f"📄 Extracted {len(text)} chars from PDF")
        except Exception as e:
            logger.error(f"PDF processing failed for {key}: {e}")
            raise

    return text


async def process_single_resume(application_id: str, nc=None):
    """Index one resume into Qdrant and mark it in MongoDB."""
    logger.info(f"⚡ STARTING: Resume {application_id}")

    if applications is None:
        logger.error("MongoDB not initialized")
        return False

    try:
        app = applications.find_one({"_id": ObjectId(application_id)})
        if not app:
            logger.error(f"Application not found: {application_id}")
            return False

        rag_uploaded = app.get("rag_uploaded", False)
        # Handle string "false" / "true" from MongoDB
        if isinstance(rag_uploaded, str):
            rag_uploaded = rag_uploaded.lower() == "true"
        
        if rag_uploaded:
            logger.info(f"✅ Resume already indexed: {application_id}")
            # Ensure we still trigger matching if it's already indexed
            job_id = app.get("jobID")
            if job_id and nc and nc.is_connected:
                message = {
                    "job_id":       str(job_id),
                    "timestamp":    datetime.now().isoformat(),
                    "triggered_by": "resume_agent_recheck",
                }
                await nc.publish("jd.match.job", json.dumps(message).encode())
                logger.info(f"📤 Re-triggered JD matching for already indexed job: {job_id}")
            return True

        resume_url = app.get("resume")
        if not resume_url:
            logger.error(f"No resume URL for application: {application_id}")
            return False

        logger.info(f"📄 Processing resume from: {resume_url}")
        text = extract_text_from_s3(resume_url)

        if not text.strip():
            logger.warning(f"No text extracted from resume: {application_id}")
            text = "No text could be extracted from this resume"

        if model and qdrant:
            logger.info("🧠 Creating embedding…")
            embedding = model.encode(text[:10000]).tolist()

            point = PointStruct(
                id=mongo_id_to_uuid(application_id),
                vector=embedding,
                payload={
                    "application_id": application_id,
                    "job_id":         str(app.get("jobID", "")),
                    "resume_text":    text[:2000],
                    "indexed_at":     datetime.now().isoformat(),
                },
            )

            logger.info("💾 Uploading to Qdrant…")
            qdrant.upsert(collection_name=QDRANT_COLLECTION, points=[point])
            logger.info("✅ Resume indexed in Qdrant")
        else:
            logger.warning("⚠️ Skipping vector index (model/qdrant not available)")

        applications.update_one(
            {"_id": app["_id"]},
            {"$set": {
                "resume_status":        "indexed",
                "rag_uploaded":         True,
                "indexed_at":           datetime.now(),
                "resume_text_extracted": text[:500],
            }},
        )
        logger.info(f"✅ Resume processed successfully: {application_id}")

        job_id = app.get("jobID")
        if job_id and nc and nc.is_connected:
            message = {
                "job_id":       str(job_id),
                "timestamp":    datetime.now().isoformat(),
                "triggered_by": "resume_agent",
            }
            await nc.publish("jd.match.job", json.dumps(message).encode())
            logger.info(f"📤 Triggered JD matching for job: {job_id}")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to process {application_id}: {e}")
        if applications:
            try:
                applications.update_one(
                    {"_id": ObjectId(application_id)},
                    {"$set": {"resume_status": "failed", "error": str(e)}},
                )
            except Exception:
                pass
        return False