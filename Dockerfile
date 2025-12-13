FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# By default, Docker will run the command from docker-compose.yml
# CMD ["python3", "cloudflare_monitor.py"]