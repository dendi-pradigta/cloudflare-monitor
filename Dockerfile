# Use a small Python base image
FROM python:3.11-slim

# Create non-root user
RUN useradd -ms /bin/bash appuser

# Install system deps (curl for healthcheck/debug)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy dependency file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app
COPY cloudflare_monitor.py .

# Switch to non-root
USER appuser

# Default environment (can be overridden via docker-compose or .env)
ENV SLEEP_INTERVAL=60

# Run the script
CMD ["python", "cloudflare_monitor.py"]
