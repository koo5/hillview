FROM tiangolo/uvicorn-gunicorn-fastapi:python3.9
COPY api/app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copy common directory
COPY common /app/common

