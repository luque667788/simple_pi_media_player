# Use ARM64 Python base image for Raspberry Pi 4
FROM arm64v8/python:3.11

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        mpv ffmpeg libgl1 libasound2 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY app/ ./app/
COPY playlist.json ./
COPY app/logging_config.py ./
COPY app/mpv_controller.py ./
COPY server.log ./
COPY restart.sh ./
COPY user_guide.md ./

# Expose Flask port
EXPOSE 5000

# Set environment variables for Flask
ENV FLASK_APP=app/main.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_ENV=production

# Entrypoint: run Flask app
CMD ["python", "app/main.py"]
