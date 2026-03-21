"""
image_enhancer.py
Enhance product images via Real-ESRGAN on Hugging Face Inference API.
Uses DUAL dedicated HF API keys per account from hf_config.json.
Falls back to PIL-based sharpening if API fails.
"""
import os
import json
import requests
from PIL import Image, ImageFilter, ImageEnhance
from io import BytesIO

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'images')
ENHANCED_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'images_enhanced')

HF_MODEL = "nightmareai/real-esrgan"
HF_API_URL = f"https://router.huggingface.co/models/{HF_MODEL}"

# Counter for alternating between dual keys
_hf_key_counter = 0


def _get_hf_key(account_id):
    """Get DEDICATED HF API key for this account (dual keys, alternating).
    Each channel has 2 keys — no borrowing from other channels."""
    global _hf_key_counter
    hf_path = os.path.join(CONFIG_DIR, 'hf_config.json')
    if not os.path.exists(hf_path):
        return ''  # No config = no key (do NOT borrow)

    with open(hf_path, 'r') as f:
        mapping = json.load(f)

    acct_map = {
        'yt_1': 'youtube_akun_1', 'yt_2': 'youtube_akun_2',
        'yt_3': 'youtube_akun_3', 'yt_4': 'youtube_akun_4',
        'yt_5': 'youtube_akun_5', 'tt_1': 'tiktok', 'fb_1': 'facebook',
    }
    config_key = acct_map.get(account_id)
    if not config_key or config_key not in mapping:
        return ''  # Unknown account — do NOT borrow other channel's key
    env_vars = mapping[config_key]
    if isinstance(env_vars, str):
        env_vars = [env_vars]
    idx = _hf_key_counter % len(env_vars)
    _hf_key_counter += 1
    return os.environ.get(env_vars[idx], '')


def enhance_via_hf(image_path, account_id='yt_1'):
    """Enhance image using Real-ESRGAN via HF API."""
    api_key = _get_hf_key(account_id)
    if not api_key:
        print(f"  [WARN] No HF API key for {account_id}, using local enhance")
        return enhance_local(image_path)

    try:
        with open(image_path, 'rb') as f:
            data = f.read()

        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.post(HF_API_URL, headers=headers, data=data, timeout=60)

        if resp.status_code == 200:
            enhanced = Image.open(BytesIO(resp.content))
            return enhanced
        else:
            print(f"  [WARN] HF API {resp.status_code}: {resp.text[:100]}")
            return enhance_local(image_path)
    except Exception as e:
        print(f"  [WARN] HF enhance failed: {e}")
        return enhance_local(image_path)


def enhance_local(image_path):
    """Local PIL-based enhancement as fallback."""
    img = Image.open(image_path).convert('RGB')

    # Sharpen
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

    # Increase contrast slightly
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.15)

    # Increase color saturation slightly
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(1.1)

    # Brightness adjustment
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.05)

    return img


def enhance_all_images(queue_file, account_id='yt_1'):
    """Enhance all product images from queue."""
    print(f"=== Image Enhancer ===")
    os.makedirs(ENHANCED_DIR, exist_ok=True)

    if not os.path.exists(queue_file):
        print(f"  Queue not found: {queue_file}")
        return

    jobs = []
    with open(queue_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                jobs.append(json.loads(line))

    total, enhanced = 0, 0
    for job in jobs:
        produk_id = job.get('produk_id', 'unknown')
        acct = job.get('account_id', account_id)

        # Find source image
        src = None
        for ext in ['jpg', 'png', 'webp']:
            p = os.path.join(DATA_DIR, f"{produk_id}.{ext}")
            if os.path.exists(p):
                src = p
                break

        if not src:
            print(f"  [SKIP] No image for {produk_id}")
            continue

        # Check if already enhanced
        out_path = os.path.join(ENHANCED_DIR, f"{produk_id}_enhanced.png")
        if os.path.exists(out_path):
            print(f"  [SKIP] Already enhanced: {produk_id}")
            total += 1
            continue

        try:
            result = enhance_via_hf(src, acct)
            result.save(out_path, 'PNG', quality=95)
            enhanced += 1
            total += 1
            print(f"  [OK] Enhanced: {produk_id}")
        except Exception as e:
            print(f"  [FAIL] {produk_id}: {e}")

    print(f"=== Enhancement complete: {enhanced}/{total} ===")


if __name__ == "__main__":
    # Pipeline-safe: just print ready message if no queue
    queue = "engine/queue/yt_queue.jsonl"
    if os.path.exists(queue):
        enhance_all_images(queue)
    else:
        print("=== Image Enhancer: No queue found, skipping ===")
