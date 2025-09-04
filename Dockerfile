# Use a lightweight Python base image
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies only if needed (kept minimal for slim image)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#  && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Create a directory for persistent data (for SQLite DB) and set permissions
RUN mkdir -p /data

# Expose the port uvicorn will listen on
EXPOSE 8000

# Default environment variables (can be overridden via docker-compose or -e)
# Persist DB to /data inside the container by default
ENV DB_PATH=/data/facebook_posts.db

# Start the FastAPI app
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
