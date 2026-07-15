# Use an official lightweight Python image
FROM python:3.11-slim

# Install system dependencies, including ffmpeg for merging video/audio streams
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside the container
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade yt-dlp

# Copy the rest of the application code
COPY . .

# Create the downloads directory
RUN mkdir -p downloads

# Expose the port the app runs on
EXPOSE 7878

# Start the application using gunicorn in production
CMD ["gunicorn", "--workers", "2", "--threads", "4", "--timeout", "120", "--bind", "0.0.0.0:7878", "app:app"]
