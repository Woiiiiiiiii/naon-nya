"""
cf_background_generator.py
Generate product backgrounds using Cloudflare Workers AI (Stable Diffusion XL).

Each account uses its OWN dedicated CF API key:
  CF_API_KEY_1 → yt_1 (fashion)
  CF_API_KEY_2 → yt_2 (gadget)
  CF_API_KEY_3 → yt_3 (beauty)
  CF_API_KEY_4 → yt_4 (home)
  CF_API_KEY_5 → yt_5 (wellness)
  CF_API_KEY_6 → tt   (fashion/beauty alternating)
  CF_API_KEY_7 → fb   (home/gadget alternating)

Output: 1080x1920 background images saved to engine/assets/backgrounds/generated/
"""

import os
import json
import random
import hashlib
import datetime
import requests
from PIL import Image, ImageFilter
from io import BytesIO

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
CF_MODEL = '@cf/stabilityai/stable-diffusion-xl-base-1.0'
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'backgrounds', 'generated')
TARGET_SIZE = (1080, 1920)  # 9:16 vertical

# Dedicated CF key per channel — NO sharing
ACCOUNT_CF_MAP = {
    'fashion':  1,   # yt_1 → CF_API_KEY_1
    'gadget':   2,   # yt_2 → CF_API_KEY_2
    'beauty':   3,   # yt_3 → CF_API_KEY_3
    'home':     4,   # yt_4 → CF_API_KEY_4
    'wellness': 5,   # yt_5 → CF_API_KEY_5
    'tt':       6,   # TikTok → CF_API_KEY_6
    'fb':       7,   # Facebook → CF_API_KEY_7
}

# Category-specific prompts for professional product backgrounds
CATEGORY_PROMPTS = {
    'fashion': [
        "elegant white marble table surface, soft natural window light, fashion product photography, minimal, clean, bokeh background, professional studio, 8k",
        "wooden rustic table, soft draped fabric, fashion accessories flatlay, warm natural lighting, elegant, professional photography, 8k",
        "smooth concrete surface, fashion studio setup, soft shadows, neutral tones, minimal aesthetic, product photography, 8k",
        "pink velvet surface, golden accents, luxury fashion styling, soft studio lighting, premium feel, elegant background, 8k",
        "beige linen tablecloth, eucalyptus leaves, boho fashion styling, natural light, aesthetic flatlay background, 8k",
    ],
    'gadget': [
        "dark matte desk surface, RGB ambient lighting, tech workspace, neon blue glow, modern, futuristic product photography, 8k",
        "black carbon fiber texture surface, blue LED accents, tech gadget photography, dark moody, professional, 8k",
        "clean white desk, minimalist tech setup, soft diffused lighting, modern workspace, Apple-style photography, 8k",
        "dark wood desk, mechanical keyboard visible, monitor glow, tech reviewer setup, ambient lighting, 8k",
        "brushed aluminum surface, gradient dark to light, tech product showcase, studio lighting, premium feel, 8k",
    ],
    'beauty': [
        "pink marble surface, fresh rose petals scattered, beauty skincare flatlay, soft pastel lighting, aesthetic, 8k",
        "white vanity table, soft pink bokeh, beauty product photography, dreamy feminine aesthetic, studio lighting, 8k",
        "terrazzo surface pattern, dried flowers, cosmetics styling, bright airy natural light, minimal beauty photography, 8k",
        "frosted glass surface, lavender sprigs, beauty spa aesthetic, soft purple tones, luxury skincare photography, 8k",
        "cream silk fabric draped, gold accessories, luxury beauty styling, warm soft lighting, premium cosmetics photography, 8k",
    ],
    'home': [
        "clean white kitchen counter, marble texture, natural window light, home product photography, warm cozy, 8k",
        "light wood dining table, potted plant, home interior styling, Scandinavian minimal, natural lighting, 8k",
        "modern gray concrete countertop, kitchen herbs, home living photography, warm ambient, clean background, 8k",
        "bamboo surface texture, natural woven mat, eco home styling, bright natural light, organic aesthetic, 8k",
        "white bedsheet surface, cozy bedroom styling, soft morning light, home comfort photography, warm tones, 8k",
    ],
    'wellness': [
        "natural cork yoga mat surface, green plants, wellness lifestyle, bright natural light, healthy aesthetic, 8k",
        "light wood gym floor, morning sunlight, fitness product photography, energetic clean style, 8k",
        "smooth stone surface, bamboo elements, zen spa aesthetic, calm peaceful, wellness photography, soft light, 8k",
        "green grass outdoor surface, natural sunlight, outdoor fitness setup, healthy active lifestyle photography, 8k",
        "white towel surface, eucalyptus branch, spa wellness aesthetic, fresh clean, self-care photography, soft tones, 8k",
    ],
}


def _get_cf_credentials(account_index=None):
    """Get paired (account_id, api_key) for a DEDICATED account index.
    Each channel uses its own key — no sharing."""
    if account_index is not None:
        acc_id = os.environ.get(f'CF_ACCOUNT_ID_{account_index}', '')
        api_key = os.environ.get(f'CF_API_KEY_{account_index}', '')
        if acc_id and api_key:
            return acc_id, api_key
        # Try shared account ID with per-account key
        acc_id = os.environ.get('CF_ACCOUNT_ID', '')
        if acc_id and api_key:
            return acc_id, api_key

    # Fallback: try all pairs 1-7, pick first available
    for i in range(1, 8):
        acc_id = os.environ.get(f'CF_ACCOUNT_ID_{i}', '')
        api_key = os.environ.get(f'CF_API_KEY_{i}', '')
        if acc_id and api_key:
            return acc_id, api_key

    return None, None


def generate_background(category, seed=None, account_index=None, blur_amount=2):
    """Generate a background image using Cloudflare Stable Diffusion.
    
    Args:
        category: Product category (fashion, gadget, beauty, home, wellness)
        seed: Random seed for reproducibility (None = random)
        account_index: Which CF_API_KEY to use (1-7). If None, uses ACCOUNT_CF_MAP.
        blur_amount: Gaussian blur radius (0 = no blur, 2 = subtle, 5 = heavy)
    
    Returns:
        PIL Image (1080x1920) or None if failed
    """
    # Use dedicated key per category
    if account_index is None:
        account_index = ACCOUNT_CF_MAP.get(category)

    account_id, api_key = _get_cf_credentials(account_index)
    if not api_key or not account_id:
        print(f"  [CF-SD] No CF credentials for account {account_index} (category: {category})")
        return None

    # Pick category prompt
    prompts = CATEGORY_PROMPTS.get(category, CATEGORY_PROMPTS['home'])
    prompt = random.choice(prompts)

    if seed is None:
        seed = random.randint(1, 999999)

    # Negative prompt to avoid people/faces/text
    negative_prompt = "person, human, face, hand, finger, text, watermark, logo, writing, letters, blurry, low quality, cartoon, anime, illustration"

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CF_MODEL}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": 1024,
        "height": 1024,
        "num_steps": 20,
        "seed": seed,
    }

    try:
        print(f"  [CF-SD] Generating {category} bg (key={account_index}, seed={seed})...")
        resp = requests.post(url, headers=headers, json=payload, timeout=60)

        if resp.status_code != 200:
            print(f"  [CF-SD] HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        # CF returns raw image bytes
        content_type = resp.headers.get('content-type', '')
        if 'image' in content_type:
            img = Image.open(BytesIO(resp.content))
        elif 'json' in content_type:
            data = resp.json()
            if 'result' in data and 'image' in data['result']:
                import base64
                img_bytes = base64.b64decode(data['result']['image'])
                img = Image.open(BytesIO(img_bytes))
            else:
                print(f"  [CF-SD] Unexpected response: {str(data)[:200]}")
                return None
        else:
            img = Image.open(BytesIO(resp.content))

        # Resize to 1080x1920 (crop center for 9:16)
        img = img.convert('RGB')
        w, h = img.size

        # Scale to fill 1080x1920
        target_w, target_h = TARGET_SIZE
        scale = max(target_w / w, target_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        # Center crop
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))

        # Apply subtle blur (background should be slightly blurred for product focus)
        if blur_amount > 0:
            img = img.filter(ImageFilter.GaussianBlur(radius=blur_amount))

        print(f"  [CF-SD] Generated {category} background: {img.size}")
        return img

    except Exception as e:
        print(f"  [CF-SD] Error: {e}")
        return None


def generate_and_save(category, count=5, account_index=None):
    """Generate multiple backgrounds for a category and save to disk.
    Uses dedicated CF key per category."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cat_dir = os.path.join(OUTPUT_DIR, category)
    os.makedirs(cat_dir, exist_ok=True)

    # Use dedicated key if not specified
    if account_index is None:
        account_index = ACCOUNT_CF_MAP.get(category)

    saved = 0
    for i in range(count):
        seed = random.randint(1, 999999)
        img = generate_background(category, seed=seed, account_index=account_index)
        if img:
            filename = f"cf_sd_{category}_{seed:06d}.jpg"
            filepath = os.path.join(cat_dir, filename)
            img.save(filepath, 'JPEG', quality=90)
            saved += 1
            print(f"    Saved: {filename}")

    print(f"  [{category}] Generated {saved}/{count} backgrounds (CF key #{account_index})")
    return saved


def generate_for_product(category, product_id, account_index=None):
    """Generate a unique background for a specific product.
    Returns PIL Image (1080x1920) or None.
    """
    # Use product_id as seed for consistency (same product = same style BG)
    seed = int(hashlib.md5(product_id.encode()).hexdigest()[:8], 16) % 999999
    if account_index is None:
        account_index = ACCOUNT_CF_MAP.get(category)
    return generate_background(category, seed=seed, account_index=account_index)


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Cloudflare SD Background Generator')
    parser.add_argument('--category', type=str, default=None,
                        help='Generate for specific category')
    parser.add_argument('--count', type=int, default=5,
                        help='Number of backgrounds per category')
    parser.add_argument('--all', action='store_true',
                        help='Generate for all categories (each uses its own CF key)')
    args = parser.parse_args()

    categories = ['fashion', 'gadget', 'beauty', 'home', 'wellness']

    if args.all:
        print("=== CF SD Background Generator (dedicated key per channel) ===")
        for cat in categories:
            key_idx = ACCOUNT_CF_MAP.get(cat, 1)
            print(f"\n  {cat} → CF_API_KEY_{key_idx}")
            generate_and_save(cat, count=args.count, account_index=key_idx)
        # Also generate for TT/FB alternate categories
        tt_cat = 'fashion' if datetime.datetime.now().day % 2 == 1 else 'beauty'
        fb_cat = 'home' if datetime.datetime.now().day % 2 == 1 else 'gadget'
        print(f"\n  tt ({tt_cat}) → CF_API_KEY_6")
        generate_and_save(tt_cat, count=args.count, account_index=6)
        print(f"\n  fb ({fb_cat}) → CF_API_KEY_7")
        generate_and_save(fb_cat, count=args.count, account_index=7)
    elif args.category:
        key_idx = ACCOUNT_CF_MAP.get(args.category, 1)
        generate_and_save(args.category, count=args.count, account_index=key_idx)
    else:
        print("Usage: --category <name> or --all")
        print(f"Categories: {', '.join(categories)}")
        print(f"Key mapping: {ACCOUNT_CF_MAP}")

