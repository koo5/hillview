FROM python:3.12-slim

RUN mkdir -p /tmp
RUN chmod a=rwx,o+t /tmp

# System dependencies. Two groups: shared libs the wheels dlopen (opencv,
# torch), and the CLIs the worker shells out to (exiftool, vips, identify/
# convert, dcraw, `free` from procps). --no-install-recommends keeps
# imagemagick's ghostscript/extra-coder recommends (and cups, avahi, mariadb
# client libs, unbound ...) out of the runtime image.
#
# Trimmed 2026-08-25 (deps audit): gcc, g++, pkg-config, libpq-dev, libgdal-dev,
# gdal-bin, libgeos-dev, libproj-dev, libspatialindex-dev, libxrender-dev
# (-> libxrender1), jpegoptim, htop, mc, iotop, jnettop. Every Python dep
# installs from a wheel (pyvips builds in ABI mode either way -- there was
# never a libvips-dev here), nothing in worker/ references gdal/geos/proj/
# jpegoptim, and the ops tools are an `apt-get install` away in a console.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    imagemagick \
    libimage-exiftool-perl \
    libvips-tools \
    dcraw \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.5 /uv /bin/uv

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
    rm /tmp/requirements.txt /bin/uv
# (/bin/uv removed: install-time only, and the static binary drags its own
# Rust/Go dependency advisories into every scan of the runtime image)

# Run as non-root user
RUN groupadd --gid 1001 worker && useradd --create-home --shell /bin/bash --uid 1001 --gid 1001 worker

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


ARG MAGICK_MEMORY_LIMIT=2GiB
ARG MAGICK_MAP_LIMIT=4GiB
ARG MAGICK_DISK_LIMIT=8GiB
ARG MAGICK_WIDTH_LIMIT=65536
ARG MAGICK_HEIGHT_LIMIT=65536
ARG MAGICK_AREA_LIMIT=1GP

RUN    sed -i "s/<policy domain=\"resource\" name=\"memory\" value=\"[^\"]*\"/<policy domain=\"resource\" name=\"memory\" value=\"${MAGICK_MEMORY_LIMIT}\"/" /etc/ImageMagick-7/policy.xml \
    && sed -i "s/<policy domain=\"resource\" name=\"map\" value=\"[^\"]*\"/<policy domain=\"resource\" name=\"map\" value=\"${MAGICK_MAP_LIMIT}\"/" /etc/ImageMagick-7/policy.xml \
    && sed -i "s/<policy domain=\"resource\" name=\"disk\" value=\"[^\"]*\"/<policy domain=\"resource\" name=\"disk\" value=\"${MAGICK_DISK_LIMIT}\"/" /etc/ImageMagick-7/policy.xml \
    && sed -i "s/<policy domain=\"resource\" name=\"width\" value=\"[^\"]*\"/<policy domain=\"resource\" name=\"width\" value=\"${MAGICK_WIDTH_LIMIT}\"/" /etc/ImageMagick-7/policy.xml \
    && sed -i "s/<policy domain=\"resource\" name=\"height\" value=\"[^\"]*\"/<policy domain=\"resource\" name=\"height\" value=\"${MAGICK_HEIGHT_LIMIT}\"/" /etc/ImageMagick-7/policy.xml \
    && sed -i "s/<policy domain=\"resource\" name=\"area\" value=\"[^\"]*\"/<policy domain=\"resource\" name=\"area\" value=\"${MAGICK_AREA_LIMIT}\"/" /etc/ImageMagick-7/policy.xml


RUN chmod a=rwx,o+t /tmp

# busybox: the in-VM hard-exit tool. On x86 Firecracker only *reboot* exits the
# VM (poweroff/halt/sysrq-o dead-spin it) — `busybox reboot -f` from a root
# `fly ssh console` is the manual escape hatch for a sick-but-sshable machine.
RUN apt-get update && apt-get install -y busybox && rm -rf /var/lib/apt/lists/*

RUN chmod +x /app/worker/start*.sh

# Starts as root: boot.py binds the listen socket within ~50ms (health checks
# and proxy wakes queue instead of getting connection-refused), sets the
# guest-kernel panic sysctls (turning an eternal freeze into a 10s
# self-reboot), then drops to the unprivileged 'worker' user before exec'ing
# start.sh. The app itself never runs as root. Invoked via python3 so no
# executable bit is needed (dev bind-mounts shadow image chmods).
CMD ["python3", "/app/worker/boot.py"]

#CMD ["/usr/bin/bash"]
