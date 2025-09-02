FROM tiangolo/uvicorn-gunicorn-fastapi:python3.9
COPY api/app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copy common directory
COPY common /app/common

# Copy API app directory
COPY api/app /app/app

# Set Python path to include app directory
ENV PYTHONPATH="/app/app:/app:$PYTHONPATH"

# Copy and setup prestart script
COPY api/app/prestart.sh /app/prestart.sh
RUN chmod +x /app/prestart.sh

