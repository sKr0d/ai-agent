# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Minimal system deps. A real coding agent will likely want git/build tooling;
# add what the tools you wire up need (git, curl, kubectl, ...).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install deps first so they are cached independently of app code.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as non-root.
RUN useradd -m agent && chown -R agent /app
USER agent

EXPOSE 8000

# Liveness probe target: the /health endpoint, wired to k8s later.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000"]
