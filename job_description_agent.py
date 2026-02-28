import os
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from bs4 import BeautifulSoup
import re

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

QDRANT_COLLECTION = "resumes"

print("🎯 JD Agent Starting...")

# MongoDB Connection
mongo = MongoClient(MONGO_URI)
db = mongo["ats"]

companies = db["companies"]
applications = db["applications"]
jobs = db["jobs"]
job_statuses = db["job-statuses"]

# Qdrant Connection - Using new client
try:
    qdrant = QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY
    )
    print("✅ Qdrant Connected")
except Exception as e:
    print(f"❌ Qdrant Connection Error: {e}")
    qdrant = None

# Initialize the embedding model
try:
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    print("✅ Model Loaded")
except Exception as e:
    print(f"❌ Model Loading Error: {e}")
    model = None

print("✅ JD Agent Ready\n")


def clean_html(html):
    """Clean HTML content and return plain text"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def process_company_jd_matching(company):
    """Process JD matching for a specific company using new Qdrant query_points method"""
    
    if qdrant is None or model is None:
        print("❌ Qdrant or Model not initialized. Skipping...")
        return
    
    company_selected = 0
    company_rejected = 0

    company_id = company["_id"]
    company_name = company.get("name", "Unknown")

    print(f"\n🏢 Company: {company_name}")
    print(f"🆔 Company ID: {company_id}")

    # Get open status for the company
    try:
        open_status = job_statuses.find_one({
            "company_id": ObjectId(company_id),
            "jobStatus": "Open"
        })
    except Exception as e:
        print(f"❌ Error finding open status: {e}")
        return

    if not open_status:
        print("⚠️ No Open Status found for this company")
        return

    # Get all open jobs for this company
    try:
        open_jobs = list(jobs.find({
            "company_id": ObjectId(company_id),
            "status": str(open_status["_id"])
        }))
        print(f"📊 Open Jobs: {len(open_jobs)}")
    except Exception as e:
        print(f"❌ Error finding open jobs: {e}")
        return

    for job in open_jobs:
        job_id = str(job["_id"])
        job_title = job.get("title", "Unknown")
        desc = job.get("description", "")

        if not desc:
            print(f"⚠️ Job {job_id} has no description, skipping...")
            continue

        print(f"\n📋 Processing Job: {job_title}")
        print(f"🆔 Job ID: {job_id}")

        # Create vector from job description
        try:
            cleaned_desc = clean_html(desc)
            vector = model.encode(cleaned_desc).tolist()
            print(f"✅ Created embedding vector")
        except Exception as e:
            print(f"❌ Error creating embedding: {e}")
            continue

        # Search in Qdrant using NEW query_points method
        try:
            # NEW METHOD: Using query_points (qdrant-client >= 1.10.0)
            print("📡 Using query_points method")
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
                    # Create a simple object with score and payload attributes
                    class SearchResult:
                        def __init__(self, score, payload):
                            self.score = score
                            self.payload = payload
                    
                    results.append(SearchResult(point.score, point.payload))
            
            print(f"📊 Found {len(results)} total results")

            # Filter results for this specific job
            filtered_results = []
            for r in results:
                if r.payload and r.payload.get("job_id") == job_id:
                    filtered_results.append(r)
            
            results = filtered_results
            print(f"📊 Found {len(results)} results for this job")

            if not results:
                print("⚠️ No results found for this job")
                continue

            # Calculate scores and cutoff
            scores = [r.score for r in results]
            best = max(scores)
            cutoff = best * 0.60
            print(f"📈 Best score: {best:.4f}, Cutoff: {cutoff:.4f}")

            job_selected = 0
            job_rejected = 0

            for r in results:
                app_id = r.payload.get("application_id")
                score = r.score

                if not app_id:
                    print("⚠️ No application_id in payload, skipping...")
                    continue

                status = "selected" if score >= cutoff else "rejected"

                if status == "selected":
                    job_selected += 1
                    company_selected += 1
                else:
                    job_rejected += 1
                    company_rejected += 1

                # Update application status in MongoDB
                try:
                    applications.update_one(
                        {"_id": ObjectId(app_id)},
                        {"$set": {"resume_status": status}}
                    )
                    print(f"✅ {app_id} - Score: {score:.4f} - Status: {status}")
                except Exception as e:
                    print(f"❌ Error updating application {app_id}: {e}")

            print(f"📊 Job Results - Selected: {job_selected}, Rejected: {job_rejected}")

        except Exception as e:
            print(f"❌ Qdrant query_points error: {e}")
            continue

    print(f"\n📊 Company Results for {company_name} → Selected: {company_selected}, Rejected: {company_rejected}")


def jd_matching_agent():
    """Run JD matching for all companies with AI features enabled - Called from main.py"""
    
    print("\n" + "="*50)
    print("🚀 Starting JD Matching for all companies")
    print("="*50)
    
    if qdrant is None or model is None:
        print("❌ Cannot run JD matching: Qdrant or Model not initialized")
        return

    try:
        companies_ai = list(companies.find({"aiFeaturesEnabled": True}))
        print(f"🏢 AI Companies found: {len(companies_ai)}")

        if not companies_ai:
            print("⚠️ No companies with AI features enabled")
            return

        for c in companies_ai:
            try:
                process_company_jd_matching(c)
            except Exception as e:
                print(f"❌ Error processing company {c.get('name', 'Unknown')}: {e}")
                continue

    except Exception as e:
        print(f"❌ Error fetching companies: {e}")
    
    finally:
        print("\n" + "="*50)
        print("✅ JD Matching Finished")
        print("="*50 + "\n")