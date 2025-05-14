FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY wait-for-mysql.sh .
COPY backend/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/
COPY frontend/ /app/frontend/

RUN chmod +x /app/wait-for-mysql.sh

CMD ["/app/wait-for-mysql.sh", "mysql", "python", "server.py"]
