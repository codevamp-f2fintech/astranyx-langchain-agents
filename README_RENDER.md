# Deploying resume_agent to Render

Background worker that indexes resumes from S3 → Qdrant and runs JD matching.

## Files
- `resume_agent.py` — agent script (index + matching)
- `Dockerfile` — builds image with system deps (tesseract, poppler)
- `requirements-render.txt` — trimmed runtime dependencies
- `render.yaml` — Render Blueprint for one-click deploy
- `.dockerignore` — excludes local files from image

---

## Local preflight

1. Ensure Docker Desktop is running:
```bash
docker version
```

2. Create `.env` with the required env vars (see `render.yaml` for the list).

3. Build the image:
```bash
docker build -t resume-agent:local .
```

4. Run with your local `.env`:
```bash
docker run --rm --env-file .env resume-agent:local
```

---

## Deploy to Render

### Option A: Blueprint (recommended)
1. Push this repo to GitHub
2. In Render: **New → Blueprint** → connect repo → select branch
3. Render reads `render.yaml` and creates the Background Worker
4. Enter the secret env vars in the Render dashboard when prompted
5. Deploy

### Option B: Manual
1. In Render: **New → Background Worker** → connect repo → select branch
2. Set **Environment** to **Docker**
3. Add these env vars in the dashboard:
   - `MONGODB_URI`
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`
   - `AWS_S3_BUCKET`
   - `QDRANT_URL`
   - `QDRANT_API_KEY`
   - Optional: `AGENT` (index|matching|both), `MODEL_NAME`, `BATCH_SIZE`
4. Choose an instance with **at least 1 GB RAM** (Starter plan or above)
5. Deploy

---

## Troubleshooting
- **OOM on Render**: upgrade to a plan with more RAM (embedding model needs ~1-2 GB)
- **Build fails**: check Docker Desktop memory settings, or try `python:3.10-bullseye` base image
- **Missing system binaries**: add apt packages to `Dockerfile`