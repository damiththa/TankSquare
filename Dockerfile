FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy TankSquare application code (No .env files are ever baked into the image;
# Cloud Run injects configuration via env vars and Google Cloud Secret Manager)
COPY app ./app

EXPOSE 8080

# Cloud Run entrypoint
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
