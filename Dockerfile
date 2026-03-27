FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD gunicorn assembler:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
