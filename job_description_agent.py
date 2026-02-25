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

mongo = MongoClient(MONGO_URI)
db = mongo["ats"]

companies = db["companies"]
applications = db["applications"]
jobs = db["jobs"]
job_statuses = db["job-statuses"]

qdrant = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)

model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2"
)

print("✅ JD Agent Ready")


def clean_html(html):

    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text(separator=" ")

    text = re.sub(r"\s+", " ", text)

    return text


def jd_matching_agent(company):

    company_selected = 0
    company_rejected = 0

    company_id = company["_id"]

    print("\nCompany:", company.get("name"))

    open_status = job_statuses.find_one({

        "company_id": ObjectId(company_id),

        "jobStatus": "Open"

    })

    if not open_status:

        print("No Open Status")

        return

    open_jobs = list(jobs.find({

        "company_id": ObjectId(company_id),

        "status": str(open_status["_id"])

    }))

    print("Open Jobs:", len(open_jobs))

    for job in open_jobs:

        job_id = str(job["_id"])

        desc = job.get("description", "")

        if not desc:

            continue

        print("\nJob:", job_id)

        vector = model.encode(

            clean_html(desc)

        ).tolist()

        try:

            results = qdrant.search(

                collection_name=QDRANT_COLLECTION,

                query_vector=vector,

                limit=10000,

                with_payload=True

            )

            results = [

                r for r in results

                if r.payload.get("job_id") == job_id

            ]

            if not results:

                continue

            scores = [

                r.score for r in results

            ]

            best = max(scores)

            cutoff = best * 0.60

            job_selected = 0
            job_rejected = 0

            for r in results:

                app_id = r.payload.get(

                    "application_id"

                )

                score = r.score

                status = "selected" if score >= cutoff else "rejected"

                if status == "selected":

                    job_selected += 1
                    company_selected += 1

                else:

                    job_rejected += 1
                    company_rejected += 1

                applications.update_one(

                    {"_id": ObjectId(app_id)},

                    {"$set": {

                        "resume_status": status

                    }}

                )

                print(app_id, score, status)

            print(

                "Selected:", job_selected,
                "Rejected:", job_rejected

            )

        except Exception as e:

            print("Qdrant Error:", e)

    print(

        "\nCompany Result →",
        "Selected:", company_selected,
        "Rejected:", company_rejected

    )


def run_jd_matching():

    companies_ai = list(

        companies.find({

            "aiFeaturesEnabled": True

        })

    )

    print("AI Companies:", len(companies_ai))

    for c in companies_ai:

        jd_matching_agent(c)

    mongo.close()

    print("✅ JD Matching Finished")