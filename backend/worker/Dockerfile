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

# Install CPU-only PyTorch first (much smaller than CUDA version)
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install opencv-python-headless (smaller than full opencv-python)
RUN pip install --no-cache-dir opencv-python-headless==4.8.1.78

# Install ultralytics (will use already installed CPU-only torch)
RUN pip install --no-cache-dir ultralytics

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
RUN mkdir -p /home/worker/.config/Ultralytics

RUN chown -R worker:worker /app/uploads
RUN chown -R worker:worker /app/pics
RUN chown -R worker:worker /home/worker/
RUN chown -R worker:worker /home/worker/.config/
RUN chown -R worker:worker /home/worker/.config/Ultralytics

# Copy application code
COPY common /app/common
COPY worker/models /app/worker/models
COPY worker/start*.sh /app/worker/
COPY worker/*py /app/worker/
COPY worker/.env /app/worker/

RUN chown -R worker:worker /app

USER worker
RUN chmod +x /app/worker/start*.sh
CMD /app/worker/start.sh
