FROM python:3.12-slim

RUN mkdir -p /tmp
RUN chmod a=rwx,o+t /tmp

# Install system dependencies for image processing and geospatial operations
RUN apt-get update && apt-get install -y \
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
    procps \
    htop \
    mc \
    iotop \
    jnettop \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy workspace root files
COPY pyproject.toml uv.lock /app/

# Copy workspace member pyproject.toml files
COPY common/pyproject.toml /app/common/
COPY worker/pyproject.toml /app/worker/

# Install worker dependencies from workspace lockfile
# Export only the worker package deps, filter platform markers for Linux
RUN uv export --frozen --no-hashes --no-emit-project --package hillview-worker | \
    grep -v "sys_platform == 'darwin'" | \
    sed "s/ ; sys_platform != 'darwin'//" > /tmp/requirements.txt && \
    uv pip install --system --no-deps \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --index-strategy unsafe-best-match \
    -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Run as non-root user
RUN useradd --create-home --shell /bin/bash worker

# Create uploads directory structure
RUN mkdir -p /app/uploads/opt \
    && mkdir -p /app/pics \
    && mkdir -p /home/worker/.config/Ultralytics

RUN chown -R worker:worker /app/uploads \
    && chown -R worker:worker /app/pics \
    && chown -R worker:worker /home/worker/

WORKDIR /app/worker

# Copy application code
COPY common /app/common
COPY worker/models /app/worker/models
COPY worker/start*.sh /app/worker/
COPY worker/*.py /app/worker/
COPY worker/.env /app/worker/

# Precompile Python bytecode for faster startup
RUN python -m compileall -b /app

RUN chown -R worker:worker /app


RUN    sed -i 's/<policy domain="resource" name="memory" value="[^"]*"/<policy domain="resource" name="memory" value="2GiB"/' /etc/ImageMagick-7/policy.xml \
    && sed -i 's/<policy domain="resource" name="map" value="[^"]*"/<policy domain="resource" name="map" value="4GiB"/' /etc/ImageMagick-7/policy.xml \
    && sed -i 's/<policy domain="resource" name="disk" value="[^"]*"/<policy domain="resource" name="disk" value="8GiB"/' /etc/ImageMagick-7/policy.xml \
    && sed -i 's/<policy domain="resource" name="width" value="[^"]*"/<policy domain="resource" name="width" value="65536"/' /etc/ImageMagick-7/policy.xml \
    && sed -i 's/<policy domain="resource" name="height" value="[^"]*"/<policy domain="resource" name="height" value="65536"/' /etc/ImageMagick-7/policy.xml \
    && sed -i 's/<policy domain="resource" name="area" value="[^"]*"/<policy domain="resource" name="area" value="1GP"/' /etc/ImageMagick-7/policy.xml



USER worker
RUN chmod +x /app/worker/start*.sh

CMD ["/app/worker/start.sh"]

#CMD ["/usr/bin/bash"]
