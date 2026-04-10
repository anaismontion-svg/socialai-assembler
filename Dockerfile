FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    fonts-dejavu-core \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Installer les polices via pip
RUN pip install fonttools && \
    mkdir -p /app/fonts && \
    python -c "
import urllib.request
urls = [
    ('https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Light.ttf', '/app/fonts/Poppins-Light.ttf'),
    ('https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf', '/app/fonts/Poppins-Regular.ttf'),
    ('https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Medium.ttf', '/app/fonts/Poppins-Medium.ttf'),
    ('https://github.com/google/fonts/raw/main/ofl/lora/Lora-Regular.ttf', '/app/fonts/Lora-Variable.ttf'),
    ('https://github.com/google/fonts/raw/main/ofl/lora/Lora-Italic.ttf', '/app/fonts/Lora-Italic-Variable.ttf'),
]
for url, path in urls:
    try:
        urllib.request.urlretrieve(url, path)
        print(f'OK: {path}')
    except Exception as e:
        print(f'SKIP: {path} — {e}')
"

COPY . .

CMD gunicorn assembler:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
