FROM python:3.12-slim

WORKDIR /app

# Install git for code fix service
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

# SQLite data persisted via volume
VOLUME /app/data

EXPOSE 8087

CMD ["python", "-m", "src.bot"]
