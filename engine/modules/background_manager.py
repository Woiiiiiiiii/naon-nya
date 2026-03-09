"""
background_manager.py
Manages background assets per category from Unsplash + Pexels APIs.

Features:
  - Local cache: engine/assets/backgrounds/[category]/
  - API fetch only when local stock < 20 per category
  - Unsplash: 50 req/hour limit
  - Pexels: 200 req/hour limit
  - Keyword mapping from category_router

Usage:
  python engine/modules/background_manager.py              # Restock all categories
  python engine/modules/background_manager.py --category fashion  # Restock one
"""
import os
import sys
import json
import random
import hashlib
import time
import requests
from PIL import Image
from io import BytesIO

# Add parent for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from engine.modules.category_router import get_all_categories, get_background_keywords, get_video_keywords

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'backgrounds', 'photo')
VIDEO_ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'backgrounds', 'video')
MIN_STOCK = 20          # Minimum photos per category before API fetch
MIN_VIDEO_STOCK = 10    # Minimum videos per category before API fetch
FETCH_COUNT = 10        # How many to fetch per API call
TARGET_SIZE = (1080, 1920)  # 9:16 vertical for Shorts

# API keys from environment (GitHub Secrets)
UNSPLASH_KEY = os.environ.get('UNSPLASH_ACCESS_KEY', '')
PEXELS_KEY = os.environ.get('PEXELS_API_KEY', '')


def get_bg_dir(category):
    """Get background directory path for a category."""
    d = os.path.join(ASSETS_DIR, category)
    os.makedirs(d, exist_ok=True)
    return d


def count_local(category):
    """Count local background images for a category."""
    d = get_bg_dir(category)
    return len([f for f in os.listdir(d) if f.endswith(('.jpg', '.png', '.webp'))])


def _save_image(img_bytes, category, source_id):
    """Save and resize image to category folder."""
    try:
        img = Image.open(BytesIO(img_bytes)).convert('RGB')

        # Crop to 9:16 aspect ratio
        w, h = img.size
        target_ratio = 9 / 16
        current_ratio = w / h

        if current_ratio > target_ratio:
            # Image is wider — crop sides
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        else:
            # Image is taller — crop top/bottom
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            img = img.crop((0, top, w, top + new_h))

        img = img.resize(TARGET_SIZE, Image.LANCZOS)

        # Save with hash-based filename
        file_hash = hashlib.md5(img_bytes[:1024]).hexdigest()[:10]
        filename = f"bg_{category}_{source_id}_{file_hash}.jpg"
        filepath = os.path.join(get_bg_dir(category), filename)

        if not os.path.exists(filepath):
            img.save(filepath, 'JPEG', quality=85)
            return filepath
        return None  # Already exists

    except Exception as e:
        print(f"    [WARN] Image save failed: {e}")
        return None


def fetch_unsplash(category, keywords, count=5):
    """Fetch backgrounds from Unsplash API."""
    if not UNSPLASH_KEY:
        print("  [--] Unsplash: no API key")
        return 0

    saved = 0
    query = random.choice(keywords)
    url = "https://api.unsplash.com/search/photos"
    params = {
        'query': query,
        'per_page': count,
        'orientation': 'portrait',
        'client_id': UNSPLASH_KEY,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 403:
            print("  [WARN] Unsplash rate limited")
            return 0
        resp.raise_for_status()
        data = resp.json()

        for photo in data.get('results', []):
            img_url = photo['urls'].get('regular', photo['urls']['small'])
            img_resp = requests.get(img_url, timeout=15)
            if img_resp.status_code == 200:
                path = _save_image(img_resp.content, category, f"un{photo['id'][:6]}")
                if path:
                    saved += 1
                    print(f"    [OK] Unsplash: {os.path.basename(path)}")

    except Exception as e:
        print(f"  [WARN] Unsplash error: {e}")

    return saved


def fetch_pexels(category, keywords, count=5):
    """Fetch backgrounds from Pexels API."""
    if not PEXELS_KEY:
        print("  [--] Pexels: no API key")
        return 0

    saved = 0
    query = random.choice(keywords)
    url = "https://api.pexels.com/v1/search"
    headers = {'Authorization': PEXELS_KEY}
    params = {
        'query': query,
        'per_page': count,
        'orientation': 'portrait',
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 429:
            print("  [WARN] Pexels rate limited")
            return 0
        resp.raise_for_status()
        data = resp.json()

        for photo in data.get('photos', []):
            img_url = photo['src'].get('large2x', photo['src']['large'])
            img_resp = requests.get(img_url, timeout=15)
            if img_resp.status_code == 200:
                path = _save_image(img_resp.content, category, f"px{photo['id']}")
                if path:
                    saved += 1
                    print(f"    [OK] Pexels: {os.path.basename(path)}")

    except Exception as e:
        print(f"  [WARN] Pexels error: {e}")

    return saved


def get_random_background(category):
    """Get a random background image path for a category."""
    d = get_bg_dir(category)
    files = [f for f in os.listdir(d) if f.endswith(('.jpg', '.png', '.webp'))]
    if not files:
        return None
    return os.path.join(d, random.choice(files))


def restock_category(category):
    """Restock backgrounds for a category if below minimum."""
    current = count_local(category)
    keywords = get_background_keywords(category)

    if current >= MIN_STOCK:
        print(f"  [{category}] Stock OK: {current} backgrounds (min={MIN_STOCK})")
        return

    need = MIN_STOCK - current
    print(f"  [{category}] Low stock: {current}/{MIN_STOCK} — fetching {need}...")

    total = 0
    if keywords and (UNSPLASH_KEY or PEXELS_KEY):
        # Try API fetch
        half = max(need // 2, 3)
        if UNSPLASH_KEY:
            total += fetch_unsplash(category, keywords, count=half)
        if PEXELS_KEY:
            total += fetch_pexels(category, keywords, count=half)

    # If API got nothing, generate placeholders
    new_count = count_local(category)
    if new_count < 5:
        print(f"  [{category}] API insufficient ({new_count}), generating placeholders...")
        generate_placeholder_bg(category, count=max(10, MIN_STOCK - new_count))
        new_count = count_local(category)

    print(f"  [{category}] Restocked: {new_count} backgrounds")


def restock_all():
    """Restock all categories."""
    print("=== Background Manager: Restock All Categories ===")

    for category in get_all_categories():
        restock_category(category)

    print("\n=== Restock complete ===")
    for category in get_all_categories():
        count = count_local(category)
        status = "[OK]" if count >= MIN_STOCK else "[LOW]"
        print(f"  {status} {category}: {count} backgrounds")


def generate_placeholder_bg(category, count=5):
    """Generate simple gradient placeholder backgrounds (fallback when no API)."""
    from PIL import ImageDraw
    import colorsys

    d = get_bg_dir(category)
    generated = 0

    # Category-based base colors
    base_hues = {
        'fashion': 0.92,   # Pink-ish
        'gadget': 0.55,    # Cyan
        'beauty': 0.85,    # Rose
        'home': 0.08,      # Orange
        'wellness': 0.35,  # Green
    }

    base_hue = base_hues.get(category, 0.5)

    for i in range(count):
        img = Image.new('RGB', TARGET_SIZE)
        draw = ImageDraw.Draw(img)

        # Generate gradient with slight hue variation
        hue = (base_hue + random.uniform(-0.05, 0.05)) % 1.0
        for y in range(TARGET_SIZE[1]):
            ratio = y / TARGET_SIZE[1]
            # Dark at top, slightly lighter at bottom
            lightness = 0.08 + ratio * 0.15
            saturation = 0.6 + random.uniform(-0.1, 0.1)
            r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
            draw.line([(0, y), (TARGET_SIZE[0], y)],
                      fill=(int(r*255), int(g*255), int(b*255)))

        # Add subtle bokeh circles
        for _ in range(random.randint(3, 8)):
            cx = random.randint(0, TARGET_SIZE[0])
            cy = random.randint(0, TARGET_SIZE[1])
            radius = random.randint(40, 150)
            alpha_val = random.randint(10, 30)
            r, g, b = colorsys.hls_to_rgb(hue, 0.3, 0.4)
            draw.ellipse([cx-radius, cy-radius, cx+radius, cy+radius],
                        fill=(int(r*255), int(g*255), int(b*255), alpha_val))

        filename = f"bg_{category}_placeholder_{i:03d}.jpg"
        filepath = os.path.join(d, filename)
        img.save(filepath, 'JPEG', quality=85)
        generated += 1

    print(f"  [{category}] Generated {generated} placeholder backgrounds")
    return generated


# ═══════════════════════════════════════════════════════════════════
#  PEXELS VIDEO BACKGROUNDS
# ═══════════════════════════════════════════════════════════════════
def get_video_bg_dir(category):
    """Get video background directory for a category."""
    d = os.path.join(VIDEO_ASSETS_DIR, category)
    os.makedirs(d, exist_ok=True)
    return d


def count_video_local(category):
    """Count local background videos for a category."""
    d = get_video_bg_dir(category)
    return len([f for f in os.listdir(d) if f.endswith(('.mp4', '.webm'))])


def fetch_pexels_video(category, keywords, count=5):
    """Fetch background videos from Pexels Video API."""
    if not PEXELS_KEY:
        print("  [--] Pexels: no API key for video fetch")
        return 0

    saved = 0
    query = random.choice(keywords) if keywords else category
    url = "https://api.pexels.com/videos/search"
    headers = {'Authorization': PEXELS_KEY}
    params = {
        'query': query,
        'per_page': count,
        'orientation': 'portrait',
        'size': 'medium',
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 429:
            print("  [WARN] Pexels video rate limited")
            return 0
        resp.raise_for_status()
        data = resp.json()

        for video_data in data.get('videos', []):
            vid_id = video_data['id']
            # Find HD or SD video file
            vid_files = video_data.get('video_files', [])
            best_url = None
            for vf in vid_files:
                # Prefer HD (720p-1080p), portrait-ish
                w = vf.get('width', 0)
                h = vf.get('height', 0)
                quality = vf.get('quality', '')
                if quality in ('hd', 'sd') and h >= 720:
                    best_url = vf['link']
                    break
            if not best_url and vid_files:
                best_url = vid_files[0]['link']

            if not best_url:
                continue

            # Download video
            filename = f"vbg_{category}_px{vid_id}.mp4"
            filepath = os.path.join(get_video_bg_dir(category), filename)
            if os.path.exists(filepath):
                continue

            try:
                vid_resp = requests.get(best_url, timeout=60, stream=True)
                if vid_resp.status_code == 200:
                    with open(filepath, 'wb') as f:
                        for chunk in vid_resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    saved += 1
                    print(f"    [OK] Pexels video: {filename}")
            except Exception as e:
                print(f"    [WARN] Video download failed: {e}")

    except Exception as e:
        print(f"  [WARN] Pexels video error: {e}")

    return saved


def get_random_video_bg(category):
    """Get a random video background path for a category."""
    d = get_video_bg_dir(category)
    files = [f for f in os.listdir(d) if f.endswith(('.mp4', '.webm'))]
    if not files:
        return None
    return os.path.join(d, random.choice(files))


def restock_video_category(category):
    """Restock video backgrounds for a category if below minimum."""
    current = count_video_local(category)
    keywords = get_video_keywords(category)

    if not keywords:
        print(f"  [{category}] No video keywords, skipping")
        return

    if current >= MIN_VIDEO_STOCK:
        print(f"  [{category}] Video stock OK: {current} (min={MIN_VIDEO_STOCK})")
        return

    need = MIN_VIDEO_STOCK - current
    print(f"  [{category}] Video low: {current}/{MIN_VIDEO_STOCK} — fetching {need}...")
    saved = fetch_pexels_video(category, keywords, count=need)
    new_count = count_video_local(category)
    print(f"  [{category}] Video restocked: +{saved} → {new_count} videos")


def restock_all_videos():
    """Restock video backgrounds for all categories."""
    print("\n=== Video Background Manager: Restock ===")
    for category in get_all_categories():
        restock_video_category(category)
    print("=== Video Restock Complete ===")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--category', type=str, default=None,
                        help='Restock specific category only')
    parser.add_argument('--placeholder', action='store_true',
                        help='Generate placeholder backgrounds (no API needed)')
    args = parser.parse_args()

    if args.placeholder:
        print("=== Generating Placeholder Backgrounds ===")
        categories = [args.category] if args.category else get_all_categories()
        for cat in categories:
            generate_placeholder_bg(cat, count=10)
    elif args.category:
        restock_category(args.category)
        restock_video_category(args.category)
    else:
        restock_all()
        restock_all_videos()
