FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    fonts-dejavu-core \
    fonts-liberation \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Télécharger Poppins et Lora depuis Google Fonts
RUN mkdir -p /app/fonts && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Light.ttf" -O /app/fonts/Poppins-Light.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf" -O /app/fonts/Poppins-Regular.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Medium.ttf" -O /app/fonts/Poppins-Medium.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/lora/Lora%5Bwght%5D.ttf" -O /app/fonts/Lora-Variable.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/lora/Lora%5Bital%2Cwght%5D.ttf" -O /app/fonts/Lora-Italic-Variable.ttf

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD gunicorn assembler:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
