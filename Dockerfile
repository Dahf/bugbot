FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

# SQLite data persisted via volume
VOLUME /app/data

EXPOSE 8087

CMD ["python", "-m", "src.bot"]
