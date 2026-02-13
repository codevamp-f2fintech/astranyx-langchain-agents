FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      tesseract-ocr \
      poppler-utils \
      libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy trimmed requirements and install
# Use requirements-render.txt to avoid installing large dev/test deps
COPY requirements-render.txt /app/requirements-render.txt
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r /app/requirements-render.txt

# Copy project files
COPY . /app

# Create non-root user for safety
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# Default command runs the agent. Use env AGENT=index|matching|both to control.
CMD ["python", "resume_agent.py"]
