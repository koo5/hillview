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
    libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*


# Upgrade pip first
RUN pip install --no-cache-dir --upgrade pip

# Pre-install large dependencies as separate layers for better caching
# Install numpy first (many packages depend on it)
RUN pip install --no-cache-dir "numpy<2"

# Install opencv-python (large package with many binary dependencies)
RUN pip install --no-cache-dir opencv-python==4.8.1.78

# Install ultralytics (includes PyTorch and other ML dependencies - very large)
RUN pip install --no-cache-dir ultralytics==8.0.196

# Install other medium-sized packages
RUN pip install --no-cache-dir \
    Pillow==10.1.0 \
    sqlalchemy==2.0.23 \
    shapely==2.0.2


WORKDIR /app/worker/

# Copy requirements and install remaining dependencies
COPY worker/requirements.txt /app/worker/requirements.txt
RUN pip install --no-cache-dir -r /app/worker/requirements.txt

# Run as non-root user
RUN useradd --create-home --shell /bin/bash worker

# Create uploads directory structure
RUN mkdir -p /app/uploads/opt
RUN mkdir -p /app/pics

RUN chown -R worker:worker /app/uploads
RUN chown -R worker:worker /app/pics

# Copy application code
COPY worker/start*.sh /app/worker/
COPY worker/*py /app/worker/
COPY worker/.env /app/worker/
COPY common /app/common

RUN chown -R worker:worker /app

USER worker
RUN chmod +x /app/worker/start*.sh
CMD /app/worker/start.sh
