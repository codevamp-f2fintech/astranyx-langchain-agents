import io
import os
import time
import uuid
import boto3
import fitz
from dotenv import load_dotenv
from pymongo import MongoClient
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer
from PIL import Image
from pdf2image import convert_from_bytes
import pytesseract

load_dotenv()

# ENV VARIABLES
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET = os.getenv("AWS_S3_BUCKET")

MONGO_URI = os.getenv("MONGODB_URI")

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

DB_NAME = "ats"
COLLECTION_NAME = "applications"
QDRANT_COLLECTION = "resumes"

BATCH_SIZE = 5

print("🤖 Resume Agent Starting...")

# AWS
s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

# MongoDB
mongo = MongoClient(MONGO_URI)
db = mongo[DB_NAME]
applications = db[COLLECTION_NAME]

# Qdrant
qdrant = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)

# Model
model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2"
)

print("✅ Resume Agent Ready")


def mongo_id_to_uuid(mongo_id):

    return str(uuid.uuid5(uuid.NAMESPACE_DNS, mongo_id))


def extract_s3_key(url):

    return url.split(".amazonaws.com/")[-1]


def extract_text_from_s3(url):

    key = extract_s3_key(url)

    obj = s3.get_object(
        Bucket=S3_BUCKET,
        Key=key
    )

    file_bytes = obj["Body"].read()

    text = ""

    # IMAGE
    if key.lower().endswith((".jpg", ".png", ".jpeg")):

        image = Image.open(io.BytesIO(file_bytes))

        text = pytesseract.image_to_string(image)

    # PDF
    else:

        with fitz.open(stream=file_bytes, filetype="pdf") as doc:

            for page in doc:

                text += page.get_text()

        if not text.strip():

            images = convert_from_bytes(file_bytes)

            for img in images:

                text += pytesseract.image_to_string(img)

    return text


def resume_indexing_agent():

    print("\n📄 Resume Indexing Started")

    query = {

        "resume": {"$exists": True},

        "resume_status": "open",

        "$or": [

            {"rag_uploaded": False},

            {"rag_uploaded": {"$exists": False}}

        ]

    }

    batch = list(
        applications.find(query).limit(BATCH_SIZE)
    )

    if not batch:

        print("✅ No resumes pending")

        return

    points = []

    for app in batch:

        app_id = str(app["_id"])

        job_id = str(app.get("jobID", ""))

        print("\nProcessing:", app_id)

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

                        "resume_text": text[:1000]

                    }

                )

            )

            applications.update_one(

                {"_id": app["_id"]},

                {"$set": {

                    "resume_status": "indexed",

                    "rag_uploaded": True

                }}

            )

            print("✅ Indexed")

        except Exception as e:

            print("❌ Failed:", e)

            applications.update_one(

                {"_id": app["_id"]},

                {"$set": {

                    "resume_status": "failed"

                }}

            )

    if points:

        qdrant.upsert(

            collection_name=QDRANT_COLLECTION,

            points=points

        )

        print("\n🚀 Uploaded to Qdrant:", len(points))

    mongo.close()

    print("✅ Resume Agent Finished")