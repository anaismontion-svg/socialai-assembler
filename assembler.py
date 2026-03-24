# assembler.py — Microservice Flask de génération de visuels Instagram
# Déployé séparément sur Railway, appelé par Node via HTTP

from flask import Flask, request, jsonify
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np
import requests
import tempfile
import os
import json
import boto3
from io import BytesIO
from supabase import create_client

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL     = os.environ.get('SUPABASE_URL')
SUPABASE_KEY     = os.environ.get('SUPABASE_SERVICE_KEY')
FONT_BASE        = '/app/fonts/'
DEFAULT_FONTS    = {
    'Lora-Italic':    'Lora-Italic-Variable.ttf',
    'Lora-Regular':   'Lora-Variable.ttf',
    'Poppins-Light':  'Poppins-Light.ttf',
    'Poppins-Regular':'Poppins-Regular.ttf',
    'Poppins-Medium': 'Poppins-Medium.ttf',
}

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────

def hex_to_rgb(hex_color):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def get_font(font_name, size):
    filename = DEFAULT_FONTS.get(font_name, 'Poppins-Light.ttf')
    path = os.path.join(FONT_BASE, filename)
    try:
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()

def download_image(url):
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return Image.open(BytesIO(r.content)).convert('RGB')

def load_logo(url, width, style='thick'):
    r = requests.get(url, timeout=15)
    logo = Image.open(BytesIO(r.content)).convert('RGBA')
    arr  = np.array(logo)
    # Détourer le fond noir
    rc, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    arr[:,:,3] = np.where((rc < 80) & (g < 80) & (b < 80), 0, arr[:,:,3])
    arr[:,:,0] = np.where(arr[:,:,3]>10, 255, 0)
    arr[:,:,1] = np.where(arr[:,:,3]>10, 255, 0)
    arr[:,:,2] = np.where(arr[:,:,3]>10, 255, 0)
    logo = Image.fromarray(arr, 'RGBA')
    # Épaisseur du trait
    dilate = {'thick': 6, 'normal': 3, 'thin': 1}.get(style, 3)
    alpha = logo.split()[3]
    for _ in range(dilate):
        alpha = alpha.filter(ImageFilter.MaxFilter(3))
    logo.putalpha(alpha)
    arr2 = np.array(logo)
    arr2[:,:,0] = np.where(arr2[:,:,3]>10, 255, 0)
    arr2[:,:,1] = np.where(arr2[:,:,3]>10, 255, 0)
    arr2[:,:,2] = np.where(arr2[:,:,3]>10, 255, 0)
    logo = Image.fromarray(arr2, 'RGBA')
    lw, lh = logo.size
    return logo.resize((width, int(lh * width / lw)), Image.LANCZOS)

def smart_crop(img, target_w, target_h):
    pw, ph = img.size
    tgt_ratio = target_w / target_h
    src_ratio = pw / ph
    if src_ratio > tgt_ratio:
        new_w = int(ph * tgt_ratio)
        left  = (pw - new_w) // 2
        img   = img.crop((left, 0, left + new_w, ph))
    else:
        new_h = int(pw / tgt_ratio)
        # Portrait → prendre depuis le haut (visage en haut)
        top = 0 if ph > pw else (ph - new_h) // 2
        top = min(top, ph - new_h)
        img = img.crop((0, top, pw, top + new_h))
    return img.resize((target_w, target_h), Image.LANCZOS)

def add_gradient(img, start_pct, max_alpha, color=(10,10,10)):
    W, H = img.size
    ov = Image.new('RGBA', (W, H), (0,0,0,0))
    d  = ImageDraw.Draw(ov)
    for y in range(int(H * start_pct), H):
        a = int(max_alpha * (y - H * start_pct) / (H * (1 - start_pct)))
        d.line([(0,y),(W,y)], fill=(*color, a))
    return Image.alpha_composite(img.convert('RGBA'), ov).convert('RGB')

def add_gradient_top(img, end_pct, max_alpha, color):
    W, H = img.size
    ov = Image.new('RGBA', (W, H), (0,0,0,0))
    d  = ImageDraw.Draw(ov)
    fade_zone = int(H * end_pct)
    for y in range(fade_zone):
        a = int(max_alpha * (1 - y / fade_zone) ** 2.2)
        d.line([(0,y),(W,y)], fill=(*color, a))
    return Image.alpha_composite(img.convert('RGBA'), ov).convert('RGB')

def paste_layer(canvas, layer, x, y):
    c = canvas.convert('RGBA')
    c.paste(layer, (x, y), layer)
    return c.convert('RGB')

def upload_to_supabase(img, filename, client_id):
    buf = BytesIO()
    img.save(buf, format='JPEG', quality=95)
    buf.seek(0)
    path = f"{client_id}/generated/{filename}"
    supabase.storage.from_('media').upload(
        path, buf.read(),
        file_options={"content-type": "image/jpeg", "upsert": "true"}
    )
    result = supabase.storage.from_('media').get_public_url(path)
    return result

def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines = []
    current = ''
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0,0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

# ─────────────────────────────────────────────────────────────────────────────
# FORMAT 1 — SINGLE POST 1080×1080
# ─────────────────────────────────────────────────────────────────────────────
def generate_single(photo_url, logo_url, branding, titre, caption):
    W, H = 1080, 1080
    palette = branding['palette']
    primary = hex_to_rgb(palette['primary'])
    light   = hex_to_rgb(palette.get('text_light', '#ffffff'))
    taupe   = hex_to_rgb(palette.get('secondary', '#c4aecf'))

    photo  = download_image(photo_url)
    photo  = ImageEnhance.Color(photo).enhance(0.88)
    canvas = smart_crop(photo, W, H)
    canvas = add_gradient(canvas, 0.46, 215)

    draw = ImageDraw.Draw(canvas)

    # Cadre fin couleur primaire
    if branding.get('frame_border', True):
        draw.rectangle([(18,18),(W-18,H-18)], outline=primary, width=1)

    # Logo
    logo_pos  = branding.get('logo_position', 'bottom-right')
    logo_size = 185
    logo = load_logo(logo_url, logo_size, branding.get('logo_style','thick'))
    if logo_pos == 'bottom-right':
        lx, ly = W - logo.width - 40, H - logo.height - 40
    elif logo_pos == 'bottom-left':
        lx, ly = 40, H - logo.height - 40
    elif logo_pos == 'top-right':
        lx, ly = W - logo.width - 40, 40
    else:  # top-left
        lx, ly = 36, 32
    canvas = paste_layer(canvas, logo, lx, ly)
    draw = ImageDraw.Draw(canvas)

    # Fonts
    ft = get_font(branding['fonts']['titre'], 56)
    fc = get_font(branding['fonts']['corps'], 29)

    # Texte — remonter depuis le bas
    caption2_y = H - 82
    caption1_y = caption2_y - 46
    sep_y      = caption1_y - 28
    titre_y    = sep_y - 72

    draw.text((56, titre_y), titre, font=ft, fill=primary)
    draw.line([(56, sep_y),(200, sep_y)], fill=primary, width=1)

    # Caption sur 2 lignes max
    lines = wrap_text(caption, fc, W - 120, draw)
    for i, line in enumerate(lines[:2]):
        draw.text((56, caption1_y + i * 44), line, font=fc,
                  fill=light if i == 0 else taupe)

    return canvas

# ─────────────────────────────────────────────────────────────────────────────
# FORMAT 2 — STORY 1080×1920
# ─────────────────────────────────────────────────────────────────────────────
def generate_story(photo_url, logo_url, branding, titre, caption, tagline):
    W, H = 1080, 1920
    palette = branding['palette']
    primary = hex_to_rgb(palette['primary'])
    light   = hex_to_rgb(palette.get('text_light', '#ffffff'))
    muted   = tuple(min(255, c + 30) for c in light)

    photo  = download_image(photo_url)
    canvas = smart_crop(photo, W, H)

    # Dégradé couleur primaire en haut
    if branding.get('gradient_top', True):
        canvas = add_gradient_top(canvas, 0.38, 115, primary)

    # Dégradé noir en bas
    canvas = add_gradient(canvas, 0.56, 220)

    # Logo en haut à gauche
    logo = load_logo(logo_url, 320, branding.get('logo_style','thick'))
    canvas = paste_layer(canvas, logo, 36, 32)

    draw = ImageDraw.Draw(canvas)
    ft = get_font(branding['fonts']['titre'], 66)
    fc = get_font(branding['fonts']['corps'], 34)
    fg = get_font(branding['fonts']['corps'], 27)

    draw.line([(80, H-372),(260, H-372)], fill=(255,255,255), width=1)
    draw.text((80, H-354), titre,                    font=ft, fill=primary)
    draw.text((80, H-272), caption,                  font=fc, fill=light)
    lines = wrap_text(caption, fc, W - 160, draw)
    y = H - 272
    for line in lines[:2]:
        draw.text((80, y), line, font=fc, fill=light)
        y += 52
    draw.text((80, H-160), tagline, font=fg, fill=muted)

    return canvas

# ─────────────────────────────────────────────────────────────────────────────
# FORMAT 3 — CAROUSEL SLIDE 1080×1080
# ─────────────────────────────────────────────────────────────────────────────
def generate_carousel_slide(photo_url, logo_url, branding, titre, caption,
                             slide_num, total_slides):
    W, H = 1080, 1080
    palette = branding['palette']
    primary = hex_to_rgb(palette['primary'])
    light   = hex_to_rgb(palette.get('text_light', '#ffffff'))
    taupe   = hex_to_rgb(palette.get('secondary', '#c4aecf'))

    photo  = download_image(photo_url)
    photo  = ImageEnhance.Color(photo).enhance(0.88)
    canvas = smart_crop(photo, W, H)
    canvas = add_gradient(canvas, 0.48, 205)

    draw = ImageDraw.Draw(canvas)

    if branding.get('frame_border', True):
        draw.rectangle([(18,18),(W-18,H-18)], outline=primary, width=1)

    # Numéro de slide
    fn = get_font(branding['fonts']['corps'], 22)
    draw.rounded_rectangle([(36,36),(130,70)], radius=14, fill=(13,13,13,170))
    draw.text((83, 53), f"{slide_num} / {total_slides}",
              font=fn, fill=primary, anchor='mm')

    # Logo
    logo = load_logo(logo_url, 185, branding.get('logo_style','thick'))
    canvas = paste_layer(canvas, logo, W - logo.width - 40, H - logo.height - 40)
    draw = ImageDraw.Draw(canvas)

    ft = get_font(branding['fonts']['titre'], 52)
    fc = get_font(branding['fonts']['corps'], 30)

    caption2_y = H - 82
    caption1_y = caption2_y - 46
    sep_y      = caption1_y - 28
    titre_y    = sep_y - 66

    draw.text((56, titre_y), titre, font=ft, fill=primary)
    draw.line([(56, sep_y),(200, sep_y)], fill=primary, width=1)

    lines = wrap_text(caption, fc, W - 120, draw)
    for i, line in enumerate(lines[:2]):
        draw.text((56, caption1_y + i * 44), line, font=fc,
                  fill=light if i == 0 else taupe)

    return canvas

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT PRINCIPAL — POST /assemble
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/assemble', methods=['POST'])
def assemble():
    try:
        data        = request.json
        client_id   = data['client_id']
        format_type = data['format']      # 'single' | 'story' | 'carousel'
        photo_urls  = data['photo_urls']  # liste d'URLs
        logo_url    = data['logo_url']
        branding    = data['branding']    # JSON complet du branding client
        titre       = data['titre']
        caption     = data['caption']
        tagline     = data.get('tagline', branding.get('tagline', ''))

        output_urls = []

        if format_type == 'single':
            img = generate_single(photo_urls[0], logo_url, branding, titre, caption)
            url = upload_to_supabase(img, f"single_{client_id}_{int(__import__('time').time())}.jpg", client_id)
            output_urls.append(url)

        elif format_type == 'story':
            img = generate_story(photo_urls[0], logo_url, branding, titre, caption, tagline)
            url = upload_to_supabase(img, f"story_{client_id}_{int(__import__('time').time())}.jpg", client_id)
            output_urls.append(url)

        elif format_type == 'carousel':
            total = len(photo_urls)
            for i, photo_url in enumerate(photo_urls):
                # Titre différent par slide — l'IA peut en envoyer plusieurs
                slide_titre = data.get('titres', [titre] * total)[i]
                slide_cap   = data.get('captions', [caption] * total)[i]
                img = generate_carousel_slide(
                    photo_url, logo_url, branding,
                    slide_titre, slide_cap,
                    i + 1, total
                )
                url = upload_to_supabase(
                    img,
                    f"carousel_{client_id}_{i+1}_{int(__import__('time').time())}.jpg",
                    client_id
                )
                output_urls.append(url)

        return jsonify({ 'success': True, 'urls': output_urls })

    except Exception as e:
        print(f"❌ Erreur assembleur: {e}")
        return jsonify({ 'success': False, 'error': str(e) }), 500

# ── Health check ──────────────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({ 'status': 'ok' })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)