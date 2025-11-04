# Gunakan image Python slim untuk ukuran kecil
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy script
COPY cloudflare_monitor.py .

# Buat direktori untuk persistensi data
RUN mkdir -p /data

# Jalankan script
CMD ["python", "cloudflare_monitor.py"]