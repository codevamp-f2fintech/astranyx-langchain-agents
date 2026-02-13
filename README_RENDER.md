# Deploying resume_agent to Render

This guide walks through local testing and deploying the `resume_agent` background worker to Render using the included `Dockerfile`.

## Files added
- `resume_agent.py` — cleaned agent script (keeps your original notebook intact).
- `Dockerfile` — builds a Docker image with system deps (tesseract, poppler).
- `.dockerignore` — excludes local files from image.
- `.env.example` — example env var names for local testing.

---

## Local preflight
1. Install Docker Desktop and ensure the Docker daemon is running.
   - On macOS: open Docker Desktop and wait until it shows "Docker is running".
   - Verify with:
```bash
docker version
```

2. Copy `.env.example` to `.env` and fill values for the required env vars.

3. Build the image locally:
```bash
docker build -t resume-agent:local .
```

4. Run the container with your local `.env`:
```bash
docker run --rm --env-file .env resume-agent:local
```

If Docker build fails during `pip install`, common fixes:
- Increase Docker Desktop memory/CPU in Preferences (embedding models and torch need RAM).
- Use a larger base image (e.g., `python:3.10-bullseye`) in `Dockerfile`.
- Create a smaller `requirements-render.txt` that contains only runtime packages required by the agent (qdrant-client, sentence-transformers, boto3, pymongo, python-dotenv, pdf2image, pytesseract, Pillow, PyMuPDF). Then copy that file into the Docker image instead of the full `requirements.txt` to avoid building dev/test packages.

Example smaller `requirements-render.txt` content:
```
qdrant-client==1.16.2
sentence-transformers==5.2.2
boto3
pymongo
python-dotenv
pdf2image
pytesseract
Pillow
PyMuPDF
```

To use it, replace the `COPY requirements.txt` and `RUN pip install -r ...` lines in `Dockerfile` with the smaller file.

---

## Push to GitHub
1. Commit the new files (keeping your notebook unchanged):
```bash
git add resume_agent.py Dockerfile .dockerignore .env.example README_RENDER.md
git commit -m "Add agent script and Dockerfile for Render deployment"
```
2. Push to your GitHub repo (replace origin URL):
```bash
git remote add origin git@github.com:USERNAME/REPO.git
git push -u origin main
```

---

## Create Render service (Docker)
1. In Render: New → Background Worker (or Private Service) → connect repo → select branch.
2. Render will use the `Dockerfile` to build the image. Set the following environment variables in the Render dashboard:
   - `MONGODB_URI`
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`
   - `AWS_S3_BUCKET`
   - `QDRANT_URL`
   - `QDRANT_API_KEY`
   - Optional: `MODEL_NAME`, `BATCH_SIZE`, `AGENT` (index|matching|both)
3. Choose an instance with enough RAM (start with 4GB; increase if you hit OOM when loading the model).
4. Deploy and monitor logs in the Render dashboard.

---

## Troubleshooting
- Docker daemon errors locally: start Docker Desktop.
- Build failures on Render due to heavy packages: use a trimmed `requirements-render.txt` as described above, or prebuild a custom image and push to a registry.
- Missing system binaries: add apt packages to `Dockerfile` (e.g., `tesseract-ocr`, `poppler-utils`).

---

If you want, I can:
- Create the `requirements-render.txt` and adjust the `Dockerfile` to use it.
- Attempt another local build once Docker is running on your machine.
- Create the GitHub commit and push (I will need your confirmation and remote URL).

Which of these should I do next?