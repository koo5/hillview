FROM python:3.9-slim

# Install system dependencies for image processing and geospatial operations
RUN apt-get update
RUN apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    libgdal-dev \
    gdal-bin \
    libgeos-dev \
    libproj-dev \
    libspatialindex-dev \
    pkg-config \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    imagemagick \
    jpegoptim \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY worker /app/

# Copy common directory  
COPY common /app/common

# Create uploads directory structure
RUN mkdir -p /app/uploads/opt

# Run as non-root user
RUN useradd --create-home --shell /bin/bash worker
RUN chown -R worker:worker /app
USER worker