FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GRIDSHIELD_DB=/data/gridshield.db \
    GRIDSHIELD_MODE=demo

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# GRIDSHIELD_MODE=demo runs the local simulator; set it to "live" to run
# cloud.ingest against a real MQTT broker instead.
CMD ["sh", "deploy/start.sh"]
