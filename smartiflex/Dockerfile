FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY bridge.py index.html logo.png ./
ENV DATA_DIR=/data
CMD ["uvicorn", "bridge:app", "--host", "0.0.0.0", "--port", "8099", "--no-proxy-headers", "--no-access-log"]
