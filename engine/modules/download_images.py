"""
download_images.py
Download product images with MULTI-TIER fallback (Shopee only).

Priority:
  Tier 1:   Shopee Cookies (authenticated API search by product name)
  Tier 2:   Shopee CDN direct (image_url from scraper)
  Tier 3:   Shopee search page scrape (find image hashes from HTML)
  Tier 4:   Shopee recommend API (alternative endpoint)
  Tier 5:   Product Collector bank (previously downloaded from Shopee)
  Tier 6:   Professional placeholder card (last resort)

No Pexels/Pixabay — all product images MUST come from Shopee.
"""
import pandas as pd
import os
import sys
import random
import re
import time
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import json

BANK_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'product_bank')

# Import proxy helper
try:
    from shopee_proxy import proxy_get, proxy_download_image, is_proxy_available
    _HAS_PROXY = True
except ImportError:
    _HAS_PROXY = False

# Rotate User-Agents to avoid blocking
_USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.101 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# Shopee session (built once, reused)
_shopee_session = None


def _build_shopee_session():
    """Build authenticated Shopee session from SHOPEE_COOKIES env var."""
    global _shopee_session
    if _shopee_session is not None:
        return _shopee_session

    cookies_raw = os.environ.get('SHOPEE_COOKIES', '')
    if not cookies_raw:
        _shopee_session = False  # Mark as attempted
        return False

    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': random.choice(_USER_AGENTS),
            'Accept': 'application/json',
            'Accept-Language': 'id-ID,id;q=0.9,en;q=0.8',
            'Referer': 'https://shopee.co.id/',
        })
        cookies = json.loads(cookies_raw)
        if isinstance(cookies, list):
            for c in cookies:
                name = c.get('name', '')
                value = c.get('value', '')
                domain = c.get('domain', '.shopee.co.id')
                if name and value:
                    session.cookies.set(name, value, domain=domain)
        elif isinstance(cookies, dict):
            for name, value in cookies.items():
                session.cookies.set(name, str(value), domain='.shopee.co.id')
        _shopee_session = session
        return session
    except Exception:
        _shopee_session = False
        return False


def _isolate_product(img, img_path):
    """Remove background using AI (rembg/HF API) and auto-crop to product bounds.
    
    Steps:
      1. Save temp file for rembg processing
      2. AI removes background → transparent PNG
      3. Auto-crop to product bounding box (tight fit)
      4. Add 5% padding so product isn't edge-to-edge
    
    Returns: clean product image (RGBA with transparent BG) or original if fails.
    """
    try:
        from engine.modules.object_isolator import isolate_via_hf
        
        # Save temp for rembg
        temp_path = img_path + '.tmp_rembg.jpg'
        img.convert('RGB').save(temp_path, 'JPEG', quality=95)
        
        # AI background removal
        result = isolate_via_hf(temp_path)
        
        # Cleanup temp
        try:
            os.remove(temp_path)
        except Exception:
            pass
        
        if result is None:
            return img
        
        # Auto-crop to product bounding box
        alpha = result.split()[3]  # Alpha channel
        bbox = alpha.getbbox()
        if bbox:
            # Add 5% padding around product
            x1, y1, x2, y2 = bbox
            pw, ph = result.size
            pad_x = int((x2 - x1) * 0.05)
            pad_y = int((y2 - y1) * 0.05)
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(pw, x2 + pad_x)
            y2 = min(ph, y2 + pad_y)
            result = result.crop((x1, y1, x2, y2))
        
        return result
        
    except Exception as e:
        print(f"    [WARN] AI isolation failed: {e}")
        return img


def _save_image(img, img_path, min_target=1620):
    """Save image with AI background removal. Returns True if saved ok."""
    w, h = img.size
    if w < 200 or h < 200:
        return False  # Too small, reject
    
    # AI background removal: isolate product, remove text/branding
    isolated = _isolate_product(img, img_path)
    
    # Save as PNG (preserves transparency) for video compositing
    png_path = os.path.splitext(img_path)[0] + '.png'
    iw, ih = isolated.size
    if iw < min_target or ih < min_target:
        scale = max(min_target / iw, min_target / ih)
        isolated = isolated.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
    
    # Save both PNG (for compositing) and JPG (for compatibility)
    if isolated.mode == 'RGBA':
        isolated.save(png_path, 'PNG')
        # Also save JPG with white background for fallback
        jpg = Image.new('RGB', isolated.size, (255, 255, 255))
        jpg.paste(isolated, mask=isolated.split()[3])
        jpg.save(img_path, 'JPEG', quality=95)
    else:
        isolated.convert('RGB').save(img_path, 'JPEG', quality=95)
    
    return True

def _score_image_simplicity(img):
    """Score how 'simple/clean' an image is. Higher = simpler = better for video.
    
    AGGRESSIVE text detection — heavily penalizes images with:
    - Text overlays (seller promotions, watermarks)
    - Multiple product variants in one image
    - Busy decorated backgrounds
    - Shopee promo bands (top/bottom colored strips)
    """
    import numpy as np
    data = np.array(img)
    h, w = data.shape[:2]
    score = 50.0  # Start neutral
    
    # 1. Edge uniformity — sample 15px border on all sides
    border = 15
    top_strip = data[:border, :, :]
    bot_strip = data[-border:, :, :]
    left_strip = data[:, :border, :]
    right_strip = data[:, -border:, :]
    
    # Low std in borders = uniform background = GOOD
    for strip in [top_strip, bot_strip, left_strip, right_strip]:
        std = strip.std()
        if std < 12:       # Very uniform (white/solid bg)
            score += 15
        elif std < 25:     # Fairly uniform
            score += 5
        elif std > 50:     # Busy border = likely has text/graphics
            score -= 20
    
    # 2. White/light percentage — more white = cleaner product photo
    brightness = data.mean(axis=2)
    white_pct = (brightness > 230).sum() / (h * w)
    score += white_pct * 50   # Up to 50 points for all-white bg
    
    # 3. TEXT DETECTION (AGGRESSIVE) — detect high-frequency edges
    gray = brightness.astype(np.uint8)
    edge_h = np.abs(gray[1:, :].astype(int) - gray[:-1, :].astype(int))
    edge_v = np.abs(gray[:, 1:].astype(int) - gray[:, :-1].astype(int))
    edge_density = (edge_h > 40).sum() + (edge_v > 40).sum()
    edge_ratio = edge_density / (h * w)
    
    if edge_ratio > 0.20:
        score -= 60  # EXTREMELY busy (guaranteed text/graphics)
    elif edge_ratio > 0.12:
        score -= 40  # Very likely has text overlays
    elif edge_ratio > 0.08:
        score -= 20  # Some text
    elif edge_ratio < 0.03:
        score += 20  # Very clean
    
    # 4. Color variety in borders — colorful borders = promo text/graphics
    for strip in [top_strip, bot_strip]:
        color_std = strip.std(axis=(0, 1))  # std per channel
        if color_std.mean() > 40:
            score -= 15  # Colorful border = promo graphics
    
    # 5. Shopee promo band detection — top/bottom 20% of image
    top_band = data[:h // 5, :, :]
    bot_band = data[-h // 5:, :, :]
    for band in [top_band, bot_band]:
        band_edge_h = np.abs(band[1:, :, :].astype(int) - band[:-1, :, :].astype(int))
        if band_edge_h.mean() > 15:
            score -= 20  # Promo band with text/graphics
    
    # 6. Center region should be dominant and CLEANER than edges
    center_h = h // 3
    center_w = w // 3
    center = data[center_h:2*center_h, center_w:2*center_w, :]
    center_brightness = center.mean()
    center_gray = center.mean(axis=2).astype(np.uint8)
    center_edge_h = np.abs(center_gray[1:, :].astype(int) - center_gray[:-1, :].astype(int))
    center_edge_ratio = (center_edge_h > 40).sum() / max(center_gray.size, 1)
    
    if center_edge_ratio < edge_ratio * 0.5:
        score += 15  # Center is much cleaner than overall = product-focused
    if 60 < center_brightness < 220:
        score += 10  # Good center content
    
    return round(max(0, score), 1)


def _download_single_image(cdn_url):
    """Download a single image from Shopee CDN. Returns PIL Image or None."""
    try:
        headers = {
            'User-Agent': random.choice(_USER_AGENTS),
            'Referer': 'https://shopee.co.id/',
        }
        if _HAS_PROXY and is_proxy_available():
            resp = proxy_get(cdn_url, headers=headers)
        else:
            resp = requests.get(cdn_url, timeout=10, headers=headers)
        if resp.status_code == 200 and len(resp.content) > 5000:
            return Image.open(BytesIO(resp.content)).convert('RGB')
    except Exception:
        pass
    return None


def _try_shopee_cookies(product_name, img_path):
    """Tier 1: Search Shopee with cookies — download ALL images, pick SIMPLEST.
    
    Shopee products have 5-9 images. Image #1 is usually the marketing image
    (full of text, logos, decorations). Later images are cleaner product shots.
    We download all, score each for simplicity, and pick the best one.
    """
    session = _build_shopee_session()
    if not session:
        return False

    try:
        url = 'https://shopee.co.id/api/v4/search/search_items'
        params = {
            'by': 'relevancy',
            'keyword': product_name,
            'limit': 3,
            'newest': 0,
            'order': 'desc',
            'page_type': 'search',
            'scenario': 'PAGE_GLOBAL_SEARCH',
            'version': 2,
        }
        time.sleep(random.uniform(0.3, 1.0))

        # Build cookie string and headers
        cookies_str = '; '.join([f"{c.name}={c.value}" for c in session.cookies])
        headers = {
            'User-Agent': random.choice(_USER_AGENTS),
            'Accept': 'application/json',
            'Referer': f'https://shopee.co.id/search?keyword={product_name.replace(" ", "+")}',
            'X-Shopee-Language': 'id',
        }

        # Try via CF proxy first
        items = None
        if _HAS_PROXY and is_proxy_available():
            from urllib.parse import urlencode
            full_url = f"{url}?{urlencode(params)}"
            resp = proxy_get(full_url, headers=headers, cookies_str=cookies_str)
            if resp.status_code == 200:
                items = resp.json().get('items', [])
        else:
            resp = session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                items = resp.json().get('items', [])

        if not items:
            return False

        # Collect ALL image candidates from ALL search results
        best_img = None
        best_score = -999
        best_label = ""

        for item_idx, item in enumerate(items[:3]):
            info = item.get('item_basic', {})
            
            # Get ALL image hashes (not just the first one!)
            image_hashes = info.get('images', [])
            if not image_hashes:
                # Fallback: single image hash
                single = info.get('image', '')
                if single:
                    image_hashes = [single]
            
            for img_idx, img_hash in enumerate(image_hashes):
                if not img_hash:
                    continue
                cdn_url = f"https://down-id.img.susercontent.com/file/{img_hash}"
                img = _download_single_image(cdn_url)
                if img is None:
                    continue
                
                # Score this image for simplicity
                score = _score_image_simplicity(img)
                label = f"item{item_idx+1}/img{img_idx+1}"
                
                if score > best_score:
                    best_score = score
                    best_img = img
                    best_label = label

        # Save the best (simplest) image
        if best_img is not None:
            if _save_image(best_img, img_path):
                tag = 'Cookies+Proxy' if (_HAS_PROXY and is_proxy_available()) else 'Cookies'
                print(f"    [OK] Shopee {tag} — picked {best_label} (score={best_score})")
                return True
        return False
    except Exception:
        return False



def _try_shopee_cdn(image_url, img_path):
    """Tier 2: Download from Shopee CDN — ALWAYS accept (this is our only URL)."""
    if not image_url or image_url == 'nan' or not image_url.startswith('http'):
        return False
    try:
        headers = {
            'User-Agent': random.choice(_USER_AGENTS),
            'Referer': 'https://shopee.co.id/',
        }
        if _HAS_PROXY and is_proxy_available():
            resp = proxy_get(image_url, headers=headers)
        else:
            resp = requests.get(image_url, timeout=15, headers=headers)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert('RGB')
        score = _score_image_simplicity(img)
        if _save_image(img, img_path):
            tag = 'CDN+Proxy' if (_HAS_PROXY and is_proxy_available()) else 'CDN'
            print(f"    [OK] Shopee {tag} (score={score})")
            return True
        print(f"    [WARN] CDN image too small")
        return False
    except Exception as e:
        print(f"    [WARN] CDN failed: {e}")
        return False


def _try_shopee_page_scrape(product_name, img_path):
    """Tier 1.5: Scrape Shopee search page — download ALL, pick SIMPLEST."""
    try:
        query = product_name.replace(' ', '+')
        url = f"https://shopee.co.id/search?keyword={query}"
        headers = {
            'User-Agent': random.choice(_USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'id-ID,id;q=0.9',
        }
        time.sleep(random.uniform(0.5, 1.5))
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        
        if resp.status_code != 200:
            return False
        
        # Find 32-char hex image hashes (Shopee CDN format)
        img_hashes = re.findall(r'([a-f0-9]{32})', resp.text)
        if not img_hashes:
            return False
        
        # Download ALL candidates, score each, pick BEST
        best_img = None
        best_score = -999
        for img_hash in img_hashes[:8]:
            cdn_url = f"https://down-id.img.susercontent.com/file/{img_hash}"
            try:
                img_resp = requests.get(cdn_url, timeout=10, headers={
                    'User-Agent': random.choice(_USER_AGENTS),
                    'Referer': 'https://shopee.co.id/',
                })
                if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                    img = Image.open(BytesIO(img_resp.content)).convert('RGB')
                    score = _score_image_simplicity(img)
                    if score > best_score:
                        best_score = score
                        best_img = img
            except Exception:
                continue
        
        if best_img is not None:
            if _save_image(best_img, img_path):
                print(f"    [OK] Shopee page scrape (score={best_score})")
                return True
        return False
    except Exception as e:
        print(f"    [WARN] Page scrape failed: {e}")
        return False


def _try_shopee_recommend(product_name, img_path):
    """Tier 1.7: Try Shopee recommend/related API for image hashes."""
    try:
        query = product_name.replace(' ', '%20')
        url = f"https://shopee.co.id/api/v4/recommend/recommend?bundle=search_related_keyword&keyword={query}&limit=3"
        headers = {
            'User-Agent': random.choice(_USER_AGENTS),
            'Accept': 'application/json',
            'Referer': f'https://shopee.co.id/search?keyword={query}',
            'X-Shopee-Language': 'id',
        }
        time.sleep(random.uniform(0.3, 1.0))
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return False
        
        # Extract image hashes from JSON response
        text = resp.text
        img_hashes = re.findall(r'([a-f0-9]{32})', text)
        for img_hash in img_hashes[:3]:
            cdn_url = f"https://down-id.img.susercontent.com/file/{img_hash}"
            try:
                img_resp = requests.get(cdn_url, timeout=10, headers={
                    'Referer': 'https://shopee.co.id/',
                })
                if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                    img = Image.open(BytesIO(img_resp.content)).convert('RGB')
                    if _save_image(img, img_path):
                        print(f"    [OK] Shopee recommend API")
                        return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def _try_product_bank(pid, category, img_path):
    """Tier 2: Copy image from Product Collector bank (previously downloaded from Shopee)."""
    # Try with category
    if category:
        bank_img = os.path.join(BANK_DIR, str(category), str(pid), 'image.jpg')
        if os.path.exists(bank_img):
            try:
                import shutil
                shutil.copy2(bank_img, img_path)
                print(f"    [OK] Product bank ({category})")
                return True
            except Exception:
                pass

    # Try all categories
    for cat in ['fashion', 'gadget', 'beauty', 'home', 'wellness']:
        bank_img = os.path.join(BANK_DIR, cat, str(pid), 'image.jpg')
        if os.path.exists(bank_img):
            try:
                import shutil
                shutil.copy2(bank_img, img_path)
                print(f"    [OK] Product bank ({cat})")
                return True
            except Exception:
                pass
    return False


def _create_placeholder(img_path, pid, name):
    """Tier 6: Professional product showcase card (last resort).
    Creates a good-looking card with gradient, product name, and price."""

    # Category-specific color palettes (gradient pairs)
    palettes = {
        'fashion': [(45, 25, 80), (130, 55, 140)],      # Deep purple gradient
        'gadget':  [(15, 30, 60), (25, 80, 140)],        # Deep blue gradient
        'beauty':  [(80, 25, 55), (170, 60, 100)],       # Rose gradient
        'home':    [(25, 55, 45), (55, 120, 80)],        # Forest gradient
        'wellness':[(30, 50, 70), (60, 130, 160)],       # Teal gradient
    }

    # Detect category from pid prefix
    cat_map = {'F': 'fashion', 'G': 'gadget', 'B': 'beauty', 'H': 'home', 'W': 'wellness'}
    category = cat_map.get(str(pid)[0].upper(), 'gadget')
    c1, c2 = palettes.get(category, [(30, 30, 50), (60, 60, 100)])

    W, H = 1080, 1080
    img = Image.new('RGB', (W, H), c1)
    draw = ImageDraw.Draw(img)

    # Draw gradient background
    for y in range(H):
        r = y / H
        cr = int(c1[0] + (c2[0] - c1[0]) * r)
        cg = int(c1[1] + (c2[1] - c1[1]) * r)
        cb = int(c1[2] + (c2[2] - c1[2]) * r)
        draw.line([(0, y), (W, y)], fill=(cr, cg, cb))

    # Draw decorative elements
    # Central display area (rounded rect effect)
    pad = 80
    rx, ry, rw, rh = pad, pad + 200, W - pad * 2, H - pad * 2 - 250
    overlay_color = (255, 255, 255, 30)
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(
        [(rx, ry), (rx + rw, ry + rh)], radius=30,
        fill=(255, 255, 255, 25)
    )
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
    draw = ImageDraw.Draw(img)

    # Load fonts
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from font_helper import get_font, get_font_bold
        fb = get_font_bold()
        fr = get_font()
        font_name = ImageFont.truetype(fb, 56) if fb else ImageFont.load_default()
        font_cat = ImageFont.truetype(fr, 32) if fr else ImageFont.load_default()
        font_big = ImageFont.truetype(fb, 120) if fb else ImageFont.load_default()
    except Exception:
        font_name = ImageFont.load_default()
        font_cat = ImageFont.load_default()
        font_big = ImageFont.load_default()

    # Category label at top
    cat_label = category.upper()
    bbox = draw.textbbox((0, 0), cat_label, font=font_cat)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 40), cat_label, font=font_cat, fill=(255, 255, 255, 180))

    # Product icon in center — PLAIN TEXT only (no emoji, fonts can't render them)
    icons = {
        'fashion': 'FASHION', 'gadget': 'GADGET', 'beauty': 'BEAUTY',
        'home': 'HOME', 'wellness': 'WELLNESS'
    }
    icon = icons.get(category, 'PRODUCT')
    try:
        bbox = draw.textbbox((0, 0), icon, font=font_name)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(((W - tw) // 2, (H - th) // 2 - 30), icon, font=font_name, fill=(255, 255, 255, 120))
    except Exception:
        pass

    # Product name (wrapped)
    words = name.split()
    lines = []
    current = ""
    for w in words:
        test = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font_name)
        if bbox[2] - bbox[0] > W - 160:
            if current:
                lines.append(current)
            current = w
        else:
            current = test
    if current:
        lines.append(current)

    y_start = H - 220
    for i, line in enumerate(lines[:3]):
        bbox = draw.textbbox((0, 0), line, font=font_name)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, y_start + i * 65), line, font=font_name, fill=(255, 255, 255))

    img.save(img_path, 'JPEG', quality=92)
    print(f"    [OK] Product card generated")


def download_images(produk_file, output_dir):
    """Download product images with multi-tier fallback.
    Shopee Cookies -> CDN -> Page Scrape -> Recommend API -> Product Bank -> Placeholder."""
    print("=== Downloading Product Images (Shopee Only) ===")
    
    if not os.path.exists(produk_file):
        print(f"Error: {produk_file} not found.")
        return
    
    os.makedirs(output_dir, exist_ok=True)
    df = pd.read_csv(produk_file)
    
    stats = {'cookies': 0, 'shopee_cdn': 0, 'shopee_scrape': 0, 'bank': 0, 'placeholder': 0, 'cached': 0}
    
    for _, row in df.iterrows():
        pid = row['produk_id']
        name = str(row.get('nama', pid))
        img_path = os.path.join(output_dir, f"{pid}.jpg")
        image_url = str(row.get('image_url', '')).strip()
        category = str(row.get('category', '')).strip()
        
        # Skip if already downloaded with good quality AND not a placeholder
        marker = img_path + '.placeholder'
        if os.path.exists(img_path) and not os.path.exists(marker):
            try:
                existing = Image.open(img_path)
                w, h = existing.size
                if w >= 400 and h >= 400:
                    stats['cached'] += 1
                    continue
            except Exception:
                pass
        # Remove old placeholder so fresh download is attempted
        if os.path.exists(marker):
            try:
                os.remove(marker)
                os.remove(img_path)
            except Exception:
                pass
        
        print(f"  [{pid}] {name[:40]}...")
        
        # TIER 1: Shopee Cookies (authenticated search)
        if _try_shopee_cookies(name, img_path):
            stats['cookies'] += 1
            continue
        
        # TIER 2: Shopee CDN (direct URL from scraper data)
        if _try_shopee_cdn(image_url, img_path):
            stats['shopee_cdn'] += 1
            continue
        
        # TIER 3: Shopee page scrape
        if _try_shopee_page_scrape(name, img_path):
            stats['shopee_scrape'] += 1
            continue
        
        # TIER 4: Shopee recommend API
        if _try_shopee_recommend(name, img_path):
            stats['shopee_scrape'] += 1
            continue
        
        # TIER 5: Product Collector bank (previously downloaded from Shopee)
        if _try_product_bank(pid, category, img_path):
            stats['bank'] += 1
            continue
        
        # TIER 6: Placeholder (last resort)
        _create_placeholder(img_path, pid, name)
        marker = img_path + '.placeholder'
        with open(marker, 'w') as mf:
            mf.write(name)
        stats['placeholder'] += 1
    
    print(f"\n  === Image Download Summary ===")
    print(f"  Cached:           {stats['cached']}")
    print(f"  Shopee Cookies:   {stats['cookies']}")
    print(f"  Shopee CDN:       {stats['shopee_cdn']}")
    print(f"  Shopee Scrape:    {stats['shopee_scrape']}")
    print(f"  Product Bank:     {stats['bank']}")
    print(f"  Placeholder:      {stats['placeholder']}")
    print(f"  Total:            {sum(stats.values())}")
if __name__ == "__main__":
    download_images(
        "engine/data/produk_valid.csv",
        "engine/data/images"
    )
