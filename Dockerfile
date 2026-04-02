# Use Python 3.12 slim for smaller image size
FROM python:3.12-slim

# Install system dependencies for audio and phonemization
RUN apt-get update && apt-get install -y \
    espeak-ng \
    libespeak-ng-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Download Kokoro model files during build
RUN python download_models.py

# Expose port (Railway dynamic port)
ENV PORT=8080
EXPOSE 8080

# Start the application using uvicorn
CMD uvicorn main:app --host 0.0.0.0 --port 8080