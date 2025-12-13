FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Secara default, Docker akan menjalankan command dari docker-compose.yml
# CMD ["python3", "cloudflare_monitor.py"]