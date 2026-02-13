import io
import os
import time
import uuid
import sys
from dotenv import load_dotenv

# Load env file if present (Render will provide env vars)
load_dotenv()

import boto3
import fitz  # PyMuPDF
from pymongo import MongoClient
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from sentence_transformers import SentenceTransformer
from PIL import Image
from pdf2image import convert_from_bytes
import pytesseract
from bs4 import BeautifulSoup
import re

def _getenv_strip(name, default=None):
    v = os.getenv(name, default)
    if v is None:
        return v
    v = v.strip()
    # Strip surrounding quotes if present
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()
    return v

# Configuration from env (with sensible defaults)
MONGO_URI = _getenv_strip("MONGODB_URI")
AWS_ACCESS_KEY = _getenv_strip("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = _getenv_strip("AWS_SECRET_ACCESS_KEY")
AWS_REGION = _getenv_strip("AWS_REGION")
S3_BUCKET = _getenv_strip("AWS_S3_BUCKET")
QDRANT_URL = _getenv_strip("QDRANT_URL")
QDRANT_API_KEY = _getenv_strip("QDRANT_API_KEY")

DB_NAME = os.getenv("DB_NAME", "ats")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "applications")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "resumes")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
MODEL_NAME = os.getenv("MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
AGENT = os.getenv("AGENT", "index")  # index | matching | both

# Remove any Windows-specific tesseract config (not needed on Linux)
# If you need a custom tesseract path, set TESSERACT_CMD env var
if os.getenv("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")

# Basic env checks
required = {
    "MONGODB_URI": MONGO_URI,
    "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY,
    "AWS_SECRET_ACCESS_KEY": AWS_SECRET_KEY,
    "AWS_REGION": AWS_REGION,
    "AWS_S3_BUCKET": S3_BUCKET,
    "QDRANT_URL": QDRANT_URL,
    "QDRANT_API_KEY": QDRANT_API_KEY,
}
missing = [k for k, v in required.items() if not v]
if missing:
    print(f"⚠️ Warning - missing env vars: {missing}")

print("\n🤖 AGENT STARTED")

# Global state for lazy loading
mongo = None
db = None
applications = None
qdrant = None
model = None
s3 = None

def init_resources():
    """Lazy load resources (model, clients) to avoid blocking import."""
    global mongo, db, applications, qdrant, model, s3
    
    # AWS client
    if not s3 and AWS_ACCESS_KEY and AWS_SECRET_KEY and AWS_REGION and S3_BUCKET:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
            region_name=AWS_REGION,
        )

    # MongoDB
    if not mongo and MONGO_URI:
        mongo = MongoClient(MONGO_URI)
        db = mongo[DB_NAME]
        applications = db[COLLECTION_NAME]

    # Qdrant
    if not qdrant and QDRANT_URL and QDRANT_API_KEY:
        qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, prefer_grpc=False, timeout=120)
        # Ensure qdrant collection exists when available
        if not qdrant.collection_exists(QDRANT_COLLECTION):
            qdrant.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )

    # Load model (may be large)
    if not model:
        try:
            print(f"⏳ Loading embedding model: {MODEL_NAME}...")
            model = SentenceTransformer(MODEL_NAME)
            print("✅ Embedding model loaded")
        except Exception as e:
            print(f"❌ Failed to load model {MODEL_NAME}: {e}")

# Helpers
def mongo_id_to_uuid(mongo_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, mongo_id))

def extract_s3_key(url: str) -> str:
    return url.split(".amazonaws.com/")[-1]

def extract_text_from_s3(url: str) -> str:
    if s3 is None:
        raise RuntimeError("S3 client not configured")
    key = extract_s3_key(url)
    print(f"   📥 Downloading: {key}")
    obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
    file_bytes = obj["Body"].read()
    text = ""

    if key.lower().endswith((".jpg", ".jpeg", ".png")):
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image)
    else:
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    text += page.get_text()
            if not text.strip():
                images = convert_from_bytes(file_bytes)
                for img in images:
                    text += pytesseract.image_to_string(img)
        except Exception:
            # fallback OCR on bytes
            images = convert_from_bytes(file_bytes)
            for img in images:
                text += pytesseract.image_to_string(img)

    if not text.strip():
        raise ValueError("No text extracted")

    print(f"   📄 Extracted {len(text)} chars")
    return text

# Agents
def resume_indexing_agent():
    init_resources()  # Verify resources are loaded
    
    if applications is None:
        print("❌ MongoDB not configured; cannot run indexing agent")
        return
    if qdrant is None:
        print("❌ Qdrant not configured; cannot run indexing agent")
        return
    if model is None:
        print("❌ Embedding model not loaded; cannot run indexing agent")
        return

    print("\n📊 MongoDB + AWS S3 + Qdrant | Starting resume indexing")

    while True:
        query = {
            "resume": {"$exists": True, "$regex": "^http"},
            "resume_status": "open",
            "$or": [
                {"rag_uploaded": False},
                {"rag_uploaded": "False"},
                {"rag_uploaded": {"$exists": False}},
            ],
        }

        pending_count = applications.count_documents(query)
        print(f"📌 Pending/open resumes count: {pending_count}")

        batch = list(applications.find(query).limit(BATCH_SIZE))
        if not batch:
            print("✅ No open resumes pending")
            break

        points = []

        for app in batch:
            app_id = str(app["_id"])
            job_id = str(app.get("jobID", ""))
            print(f"\n📄 Processing {app_id} | Job: {job_id}")
            try:
                text = extract_text_from_s3(app["resume"])
                embedding = model.encode(text).tolist()
                points.append(
                    PointStruct(
                        id=mongo_id_to_uuid(app_id),
                        vector=embedding,
                        payload={
                            "application_id": app_id,
                            "job_id": job_id,
                            "resume_text": text[:1500],
                        },
                    )
                )

                applications.update_one({"_id": app["_id"]}, {"$set": {"resume_status": "indexed", "rag_uploaded": True, "indexed_at": time.time()}})
                print("✅ Indexed")
            except Exception as e:
                applications.update_one({"_id": app["_id"]}, {"$set": {"resume_status": "failed", "error": str(e)}})
                print(f"❌ Failed → {e}")

        if points:
            qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)
            print(f"🚀 {len(points)} vectors pushed to Qdrant")

        time.sleep(1)


def clean_html(raw_html):
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def jd_matching_agent():
    init_resources()  # Verify resources are loaded
    
    if applications is None:
        print("❌ MongoDB not configured; cannot run JD matching agent")
        return
    if qdrant is None:
        print("❌ Qdrant not configured; cannot run JD matching agent")
        return
    if model is None:
        print("❌ Embedding model not loaded; cannot run JD matching agent")
        return

    print("\n🚀 JD MATCHING AGENT STARTED")
    companies = db.get("companies") if db is not None else None
    jobs = db.get("jobs") if db is not None else None
    job_statuses = db.get("job-statuses") if db is not None else None

    # find AI-enabled companies
    ai_companies = list(companies.find({"aiFeaturesEnabled": True})) if companies is not None else []
    if not ai_companies:
        print("❌ No AI enabled companies found")
        return

    for company in ai_companies:
        company_id = company["_id"]
        print(f"\n🏢 Running JD Matching For Company: {company.get('name')}")

        open_status_doc = list(job_statuses.find({"company_id": company_id, "jobStatus": "Open"}))
        if not open_status_doc:
            print("❌ No OPEN status found for company")
            continue
        open_status_id = open_status_doc[0]["_id"]

        open_jobs = list(jobs.find({"company_id": company_id, "status": str(open_status_id)}))
        if not open_jobs:
            print("❌ No OPEN jobs found")
            continue

        for job in open_jobs:
            job_id = str(job["_id"])
            job_description = job.get("description", "")
            if not job_description.strip():
                print(f"⚠️ Job {job_id} has no description")
                continue

            cleaned_description = clean_html(job_description)
            jd_vector = model.encode(cleaned_description).tolist()

            try:
                search_results = qdrant.query_points(collection_name=QDRANT_COLLECTION, query=jd_vector, limit=100000, with_payload=True, with_vectors=False).points
                search_results = [r for r in search_results if r.payload.get("job_id") == job_id]
                print(f"📊 Found {len(search_results)} resumes for this job")
                if not search_results:
                    continue

                scores = [r.score for r in search_results if r.score is not None]
                if not scores:
                    print("❌ No similarity scores found")
                    continue

                best_score = max(scores)
                cutoff = best_score * 0.63
                print(f"🏆 Best Score: {best_score:.4f}")
                print(f"🎯 Selection Cutoff (63% of Best): {cutoff:.4f}")

                for result in search_results:
                    payload = result.payload or {}
                    application_id = payload.get("application_id")
                    score = result.score
                    if not application_id or score is None:
                        continue
                    status = "selected" if score >= cutoff else "rejected"
                    applications.update_one({"_id": applications._get_id(application_id) if hasattr(applications, '_get_id') else application_id}, {"$set": {"resume_status": status}})
                    print(f"   ➜ {application_id} | {score:.4f} → {status}")

            except Exception as e:
                print(f"❌ Qdrant query failed: {e}")

    print("✅ Company JD Matching Done")


if __name__ == "__main__":
    try:
        if AGENT in ("index", "both"):
            resume_indexing_agent()
        if AGENT in ("matching", "both"):
            jd_matching_agent()
        print("\n🎯 Agent finished")
    finally:
        try:
            if mongo is not None:
                mongo.close()
                print("✅ MongoDB closed")
        except Exception:
            pass
