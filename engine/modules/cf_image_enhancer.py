"""
cf_image_enhancer.py
Enhance & beautify product images using Cloudflare Workers AI.

ROLE: Inspector + Beautifier
1. Enhance ALL composite images before video creation
2. Sharpen product details, improve contrast, clean up edges
3. Use img2img with LOW strength (0.15-0.30) to beautify without changing product

Each account uses its OWN dedicated CF API key:
  CF_API_KEY_1 → yt_1 (fashion)
  CF_API_KEY_2 → yt_2 (gadget)
  CF_API_KEY_3 → yt_3 (beauty)
  CF_API_KEY_4 → yt_4 (home)
  CF_API_KEY_5 → yt_5 (wellness)
  CF_API_KEY_6 → tt
  CF_API_KEY_7 → fb
"""

import os
import random
import requests
import base64
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from io import BytesIO

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
CF_MODEL_IMG2IMG = '@cf/stabilityai/stable-diffusion-xl-base-1.0'
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

# Enhancement prompts per category — SUBTLE beautification
ENHANCE_PROMPTS = {
    'fashion': "professional fashion product photography, sharp details, clean background, studio lighting, vibrant colors, high quality, 8k",
    'gadget': "professional tech product photography, sharp edges, clean modern look, studio lighting, high contrast, premium feel, 8k",
    'beauty': "professional beauty product photography, soft lighting, skincare aesthetic, clean elegant, haute couture, pastel tones, 8k",
    'home': "professional home product photography, warm natural light, clean minimal, cozy aesthetic, lifestyle catalog, 8k",
    'wellness': "professional wellness product photography, fresh natural, clean healthy aesthetic, bright energetic, lifestyle, 8k",
}


def _get_cf_credentials(account_index=None):
    """Get paired (account_id, api_key) for a DEDICATED account index."""
    if account_index is not None:
        acc_id = os.environ.get(f'CF_ACCOUNT_ID_{account_index}', '')
        api_key = os.environ.get(f'CF_API_KEY_{account_index}', '')
        if acc_id and api_key:
            return acc_id, api_key
        acc_id = os.environ.get('CF_ACCOUNT_ID', '')
        if acc_id and api_key:
            return acc_id, api_key

    # Fallback: try all pairs 1-7
    for i in range(1, 8):
        acc_id = os.environ.get(f'CF_ACCOUNT_ID_{i}', '')
        api_key = os.environ.get(f'CF_API_KEY_{i}', '')
        if acc_id and api_key:
            return acc_id, api_key

    return None, None


def enhance_local(img_path, category='home'):
    """Enhance image using LOCAL PIL processing (no API needed).
    
    Applied to ALL images — fast, free, always works:
    1. Auto-contrast: normalize brightness range
    2. Sharpness boost: make product details crisp
    3. Color vibrancy: slight saturation increase
    4. Edge clarity: unsharp mask for professional look
    
    Returns: enhanced PIL Image (RGB)
    """
    try:
        img = Image.open(img_path).convert('RGB')
    except Exception:
        return None

    # 1. Auto-contrast — normalize brightness
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.15)  # Slight contrast boost

    # 2. Brightness — ensure not too dark
    data = np.array(img)
    avg_brightness = data.mean()
    if avg_brightness < 100:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.2)
    elif avg_brightness > 220:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(0.95)

    # 3. Color vibrancy — slight saturation boost
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(1.1)

    # 4. Sharpness — crisp product details
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.3)

    # 5. Unsharp mask — professional edge clarity
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=3))

    print(f"    [ENHANCE] Local: contrast+sharp+color applied")
    return img


def enhance_with_cf(img_path, category='home', account_index=None, strength=0.20):
    """Enhance image using Cloudflare SD img2img (subtle beautification).
    
    Uses LOW strength (0.15-0.30) to:
    - Improve product clarity and professional look
    - Clean up edges and smooth transitions
    - Enhance lighting to match category aesthetic
    - WITHOUT changing the actual product
    
    Returns: enhanced PIL Image (RGB) or None if CF unavailable
    """
    if account_index is None:
        account_index = ACCOUNT_CF_MAP.get(category)

    account_id, api_key = _get_cf_credentials(account_index)
    if not api_key or not account_id:
        print(f"    [CF-ENHANCE] No CF credentials for {category}")
        return None

    try:
        # Load and prepare source image
        img = Image.open(img_path).convert('RGB')
        
        # Resize to 1024x1024 for SD processing (square)
        # We'll stretch back to original size after
        original_size = img.size
        img_square = img.resize((1024, 1024), Image.LANCZOS)
        
        # Convert to base64
        buffer = BytesIO()
        img_square.save(buffer, format='PNG')
        img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        prompt = ENHANCE_PROMPTS.get(category, ENHANCE_PROMPTS['home'])
        negative_prompt = "blurry, low quality, distorted, ugly, text, watermark, logo, cartoon, anime, noisy, grainy"
        
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CF_MODEL_IMG2IMG}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "image": img_b64,
            "strength": strength,   # LOW = subtle enhancement
            "num_steps": 15,        # Fewer steps = faster + subtler
            "seed": random.randint(1, 999999),
        }

        print(f"    [CF-ENHANCE] Enhancing {category} (strength={strength})...")
        resp = requests.post(url, headers=headers, json=payload, timeout=60)

        if resp.status_code != 200:
            print(f"    [CF-ENHANCE] HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        # Parse response
        content_type = resp.headers.get('content-type', '')
        if 'image' in content_type:
            result_img = Image.open(BytesIO(resp.content))
        elif 'json' in content_type:
            data = resp.json()
            if 'result' in data and 'image' in data['result']:
                img_bytes = base64.b64decode(data['result']['image'])
                result_img = Image.open(BytesIO(img_bytes))
            else:
                print(f"    [CF-ENHANCE] Unexpected response format")
                return None
        else:
            result_img = Image.open(BytesIO(resp.content))

        # Resize back to original dimensions
        result_img = result_img.convert('RGB').resize(original_size, Image.LANCZOS)

        print(f"    [CF-ENHANCE] Enhanced {category}: {result_img.size}")
        return result_img

    except Exception as e:
        print(f"    [CF-ENHANCE] Error: {e}")
        return None


def enhance_composite(img_path, category='home', account_index=None):
    """Full enhancement pipeline for a composite image.
    
    1. Always apply LOCAL enhancement (free, fast)
    2. Try CF SD enhancement if credentials available (subtle beautification)
    3. Save enhanced version back to same path
    
    Returns: True if enhanced, False if failed
    """
    # Step 1: Local enhancement (always works)
    enhanced = enhance_local(img_path, category)
    if enhanced is None:
        print(f"    [ENHANCE] Failed to load: {img_path}")
        return False

    # Save local-enhanced version
    enhanced.save(img_path, 'PNG', quality=95)

    # Step 2: Try CF SD enhancement (optional, subtle)
    cf_result = enhance_with_cf(img_path, category, account_index, strength=0.20)
    if cf_result is not None:
        cf_result.save(img_path, 'PNG', quality=95)
        print(f"    [ENHANCE] CF + Local applied → {os.path.basename(img_path)}")
    else:
        print(f"    [ENHANCE] Local only → {os.path.basename(img_path)}")

    return True


def enhance_all_composites(composites_dir, category='home', account_index=None):
    """Enhance all composite images in a directory.
    
    Called after image_compositor generates composites, before video generation.
    """
    if not os.path.exists(composites_dir):
        print(f"  [ENHANCE] Dir not found: {composites_dir}")
        return

    files = [f for f in os.listdir(composites_dir) 
             if f.endswith('.png') and 'composite' in f]
    
    if not files:
        print(f"  [ENHANCE] No composites found in {composites_dir}")
        return

    if account_index is None:
        account_index = ACCOUNT_CF_MAP.get(category)

    print(f"  [ENHANCE] Enhancing {len(files)} composites ({category})...")
    for f in files:
        fpath = os.path.join(composites_dir, f)
        enhance_composite(fpath, category, account_index)

    print(f"  [ENHANCE] Done — {len(files)} images enhanced")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=str, required=True, help='Composites directory')
    parser.add_argument('--category', type=str, default='home')
    parser.add_argument('--account', type=int, default=None)
    args = parser.parse_args()

    enhance_all_composites(args.input, args.category, args.account)
