import urllib.request
import os

os.makedirs('/app/fonts', exist_ok=True)

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
        print(f'✅ {path}')
    except Exception as e:
        print(f'❌ {path} — {e}')
