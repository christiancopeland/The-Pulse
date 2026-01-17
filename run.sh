#!/bin/bash
cd "$(dirname "$0")"

# Start existing PostgreSQL container if stopped
if ! docker ps --filter ancestor=postgres:16-alpine --format '{{.Names}}' | grep -q .; then
    echo "Starting PostgreSQL container..."
    docker start $(docker ps -a --filter ancestor=postgres:16-alpine --format '{{.Names}}' | head -1) 2>/dev/null || echo "No postgres:16-alpine container found"
else
    echo "PostgreSQL already running"
fi

# Start Qdrant container if not already running
if ! docker ps --format '{{.Names}}' | grep -q '^qdrant$'; then
    echo "Starting Qdrant container..."
    docker run -d -p 6333:6333 -p 6334:6334 \
        -v qdrant_storage:/qdrant/storage \
        qdrant/qdrant
else
    echo "Qdrant already running"
fi

# Start the FastAPI app
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
