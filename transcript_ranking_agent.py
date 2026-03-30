import os
import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
from pymongo import MongoClient
from bson.objectid import ObjectId

# -----------------------------
# LOAD ENV VARIABLES
# -----------------------------
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
QDRANT_URL = os.getenv("QDRANT_URL") 
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")  

COLLECTION_NAME = "interview_vectors"

# -----------------------------
# CONNECT MONGODB
# -----------------------------
mongo = MongoClient(MONGO_URI)
db = mongo[DB_NAME]  # default database from URI
interviews =db[COLLECTION_NAME]



# -----------------------------
# CONNECT QDRANT CLOUD
# -----------------------------
qdrant = QdrantClient(
    url=QDRANT_CLOUD_URL,
    api_key=QDRANT_CLOUD_API_KEY
)


# -----------------------------
# EMBEDDING MODEL
# -----------------------------
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
# -----------------------------


# CREATE COLLECTION IF NOT EXISTS
# -----------------------------
try:
    qdrant.get_collection(COLLECTION_NAME)
except Exception:
    qdrant.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "size": 384,
            "distance": "Cosine"
        }
    )

print("✅ Environment loaded successfully")
print("✅ MongoDB connected")
print("✅ Qdrant Cloud connected")

# -----------------------------
# FETCH INTERVIEWS
# -----------------------------
def fetch_interviews():
    return list(
        interviews_collection.find({"status": "hold"}).sort("interview_score", -1)
    )

# -----------------------------
# FETCH JOBS
# -----------------------------
def fetch_jobs():
    return list(jobs_collection.find({}))

# -----------------------------
# STORE TRANSCRIPT EMBEDDINGS
# -----------------------------
def store_transcripts(interviews):
    points = []

    for row in interviews:
        transcript = row["interview_transcript"]
        embedding = model.encode(transcript).tolist()

        point = PointStruct(
            id=str(row["_id"]),  # use MongoDB ObjectId as string
            vector=embedding,
            payload={
                "interview_id": str(row["_id"]),
                "candidate_id": row["candidate_id"],
                "job_id": row["job_id"],
                "transcript": transcript
            }
        )
        points.append(point)

    if points:
        qdrant.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )

    print(f"{len(points)} transcripts stored in Qdrant Cloud")

# -----------------------------
# SEMANTIC SEARCH
# -----------------------------
def semantic_match(job_description, job_id):
    job_vector = model.encode(job_description).tolist()

    results = qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=job_vector,
        limit=50,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="job_id",
                    match=MatchValue(value=job_id)
                )
            ]
        )
    )
    return results

# -----------------------------
# SCORE CATEGORY
# -----------------------------
def get_rank_category(score):
    if score >= 0.80:
        return "HOT"
    elif score >= 0.60:
        return "WARM"
    else:
        return "COLD"

# -----------------------------
# RANK CANDIDATES
# -----------------------------
def rank_candidates(results):
    candidates = []

    for r in results:
        score = r.score
        category = get_rank_category(score)

        candidates.append({
            "interview_id": r.payload["interview_id"],
            "candidate_id": r.payload["candidate_id"],
            "job_id": r.payload["job_id"],
            "score": score,
            "rank": category
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    print("\nCandidate Evaluation:")
    for c in candidates:
        print(f"Candidate {c['candidate_id']} | Score: {c['score']:.4f} | Rank: {c['rank']}")

    return candidates

# -----------------------------
# UPDATE INTERVIEWS IN MONGODB
# -----------------------------
def update_results(ranked):
    for c in ranked:
        interviews_collection.update_one(
            {"_id": ObjectId(c["interview_id"])},
            {"$set": {
                "interview_score": c["score"],
                "rank": c["rank"],
                "status": "evaluated"
            }}
        )

# -----------------------------
# DELETE BY JOB_ID
# -----------------------------
def delete_by_job(job_id):
    qdrant.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="job_id",
                    match=MatchValue(value=job_id)
                )
            ]
        )
    )
    print(f"✅ Deleted embeddings for job_id: {job_id}")

# -----------------------------
# MAIN AGENT
# -----------------------------
def ranking_agent():
    print("Your transcript ranking agent is started 🤖")

    print("Fetching interviews...")
    interviews = fetch_interviews()
    job_ids_with_data = set([i["job_id"] for i in interviews])

    if not interviews:
        print("No interviews found.")
        return

    print("Fetching jobs...")
    jobs = fetch_jobs()
    filtered_jobs = [job for job in jobs if job["id"] in job_ids_with_data]

    print("Generating embeddings...")
    store_transcripts(interviews)

    all_ranked = []

    print("Running semantic search...")
    for job in filtered_jobs:
        job_id = job["id"]
        description = job["description"]

        results = semantic_match(description, job_id)
        ranked = rank_candidates(results)
        all_ranked.extend(ranked)

        # 🔥 DELETE ONLY THIS JOB DATA AFTER RANKING
        delete_by_job(job_id)

    print("Updating MongoDB...")
    update_results(all_ranked)

    print("Agent 🤖 completed successfully.")

ranking_agent()
  