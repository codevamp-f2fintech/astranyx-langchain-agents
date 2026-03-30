"""
run_all.py – single entry point for the ATS pipeline.

Architecture:
  MongoDBWatcher  runs in a thread-pool executor
    └─ puts application_id into an asyncio.Queue
  queue_dispatcher  (async task) drains the queue
    └─ publishes resume.new via NATS
  ResumeAgent  subscribes resume.new -> indexes in Qdrant
  JDAgent      subscribes jd.match.job -> scores resumes

One event loop. No duplicate agents. No thread/loop conflict.
"""

import asyncio
import os
import json
import logging
from datetime import datetime

import nats
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

MONGO_URI   = os.getenv("MONGODB_URI")
NATS_SERVER = os.getenv("NATS_SERVERS", "nats://localhost:4222")


# -------------------------------------------------
# MongoDB Watcher  (runs in a thread)
# -------------------------------------------------

def watch_mongo_thread(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """
    Blocking function - runs in executor.
    Puts application_id strings onto the asyncio queue whenever
    a new document with a resume field is inserted.
    """
    import time

    mongo      = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    collection = mongo["ats"]["applications"]
    logger.info("MongoDB Watcher thread connected")

    def enqueue(app_id: str):
        asyncio.run_coroutine_threadsafe(queue.put(app_id), loop)

    try:
        mongo.admin.command("replSetGetStatus")
        logger.info("Replica-set detected - using change streams")

        pipeline = [{"$match": {"operationType": "insert"}}]
        with collection.watch(pipeline) as stream:
            for change in stream:
                doc    = change["fullDocument"]
                app_id = str(doc.get("_id"))
                if doc.get("resume"):
                    logger.info(f"Change stream: new resume -> {app_id}")
                    enqueue(app_id)

    except OperationFailure:
        logger.warning("No replica-set - falling back to polling (5 s interval)")
        last_check = datetime.now()
        while True:
            try:
                for doc in collection.find({
                    "resume":    {"$exists": True, "$ne": None},
                    "createdAt": {"$gt": last_check},
                }):
                    app_id = str(doc["_id"])
                    logger.info(f"Polling: new resume -> {app_id}")
                    enqueue(app_id)
                last_check = datetime.now()
            except Exception as exc:
                logger.error(f"Polling error: {exc}")
            time.sleep(5)


# -------------------------------------------------
# Queue dispatcher  (async task on event loop)
# -------------------------------------------------

async def queue_dispatcher(queue: asyncio.Queue, nc):
    """Drain the queue and publish each application_id over NATS."""
    logger.info("Queue dispatcher running")
    while True:
        app_id = await queue.get()
        try:
            msg = {
                "application_id": app_id,
                "timestamp":      datetime.now().isoformat(),
            }
            await nc.publish("resume.new", json.dumps(msg).encode())
            logger.info(f"Published resume.new -> {app_id}")
        except Exception as exc:
            logger.error(f"Failed to publish resume.new for {app_id}: {exc}")
        finally:
            queue.task_done()


# -------------------------------------------------
# Resume Agent subscriber
# -------------------------------------------------

async def run_resume_agent(nc):
    from resume_indexing_agent import process_single_resume

    async def handler(msg):
        try:
            data   = json.loads(msg.data.decode())
            app_id = data.get("application_id")
            logger.info(f"resume.new received -> {app_id}")
            if app_id:
                await process_single_resume(app_id, nc)
            else:
                logger.error("resume.new message missing application_id")
        except Exception as exc:
            logger.error(f"ResumeAgent handler error: {exc}", exc_info=True)

    await nc.subscribe("resume.new", cb=handler)
    logger.info("ResumeAgent subscribed to resume.new")


# -------------------------------------------------
# JD Matching Agent subscriber
# -------------------------------------------------

async def run_jd_agent(nc):
    from job_description_agent import process_job_matching

    async def handler(msg):
        try:
            data   = json.loads(msg.data.decode())
            job_id = data.get("job_id")
            logger.info(f"jd.match.job received -> {job_id}")
            if job_id:
                result = await process_job_matching(job_id, nc)
                logger.info(f"Match result: {result}")
            else:
                logger.error("jd.match.job message missing job_id")
        except Exception as exc:
            logger.error(f"JDAgent handler error: {exc}", exc_info=True)

    await nc.subscribe("jd.match.job", cb=handler)
    await nc.subscribe("jd.match.all", cb=handler)
    logger.info("JDAgent subscribed to jd.match.job + jd.match.all")


# -------------------------------------------------
# Main
# -------------------------------------------------

async def main():
    logger.info("=" * 60)
    logger.info("ATS PIPELINE STARTING")
    logger.info("=" * 60)

    nc = await nats.connect(
        NATS_SERVER,
        reconnect_time_wait=2,
        max_reconnect_attempts=20,
    )
    logger.info("NATS connected")

    # 1. Register subscribers FIRST so nothing is missed
    await run_resume_agent(nc)
    await run_jd_agent(nc)

    # 2. Queue bridges the blocking watcher thread -> async world
    queue = asyncio.Queue()

    # 3. Dispatcher lives on the event loop
    asyncio.create_task(queue_dispatcher(queue, nc))

    logger.info("=" * 60)
    logger.info("All agents ready - waiting for events")
    logger.info("Insert a resume in MongoDB to trigger the pipeline")
    logger.info("=" * 60)

    # 4. Blocking MongoDB watcher runs in thread-pool executor.
    #    Keeps main() alive and yields the event loop to handlers.
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, watch_mongo_thread, queue, loop)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")