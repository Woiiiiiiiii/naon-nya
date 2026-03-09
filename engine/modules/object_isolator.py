"""
object_isolator.py
Professional background removal via REMBG on Hugging Face Inference API.
Uses dedicated HF API key per account. Falls back to local rembg library.
Includes edge feathering and alpha cleanup for natural compositing.
"""
import os
import json
import requests
import numpy as np
from PIL import Image, ImageFilter
from io import BytesIO

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')

HF_MODEL = "briaai/RMBG-1.4"
HF_API_URL = f"https://router.huggingface.co/models/{HF_MODEL}"


def _get_hf_key(account_id):
    """Get HF API key dedicated to this account."""
    hf_path = os.path.join(CONFIG_DIR, 'hf_config.json')
    if not os.path.exists(hf_path):
        return os.environ.get('HF_API_KEY_1', '')
    with open(hf_path, 'r') as f:
        mapping = json.load(f)
    acct_map = {
        'yt_1': 'youtube_akun_1', 'yt_2': 'youtube_akun_2',
        'yt_3': 'youtube_akun_3', 'yt_4': 'youtube_akun_4',
        'yt_5': 'youtube_akun_5', 'tt_1': 'tiktok', 'fb_1': 'facebook',
    }
    config_key = acct_map.get(account_id, 'youtube_akun_1')
    env_var = mapping.get(config_key, 'HF_API_KEY_1')
    return os.environ.get(env_var, '')


def isolate_via_hf(image_path, account_id='yt_1'):
    """Remove background using HF API (RMBG-1.4)."""
    api_key = _get_hf_key(account_id)
    if not api_key:
        return isolate_local(image_path)

    try:
        with open(image_path, 'rb') as f:
            data = f.read()
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.post(HF_API_URL, headers=headers, data=data, timeout=60)
        if resp.status_code == 200:
            result = Image.open(BytesIO(resp.content)).convert('RGBA')
            return _feather_edges(result)
        else:
            print(f"  [WARN] HF RMBG {resp.status_code}")
            return isolate_local(image_path)
    except Exception as e:
        print(f"  [WARN] HF isolation failed: {e}")
        return isolate_local(image_path)


def isolate_local(image_path):
    """Local background removal using rembg library."""
    try:
        from rembg import remove
        with open(image_path, 'rb') as f:
            data = f.read()
        result = Image.open(BytesIO(remove(data))).convert('RGBA')
    except Exception:
        # Fallback: use original image as-is (jangan coba hapus BG manual)
        # karena simple white removal sering bikin produk pudar
        result = Image.open(image_path).convert('RGBA')

    return _feather_edges(result)


def _feather_edges(rgba_image):
    """Apply GENTLE edge feathering for natural blending.
    Sebelumnya: MinFilter(3) + Blur(2.5) = produk pudar.
    Sekarang: MinFilter(1) + Blur(0.8) = edge halus tapi produk tetap solid."""
    alpha = rgba_image.split()[3]
    arr = np.array(alpha)

    # Threshold: alpha < 30 -> 0 (hapus noise), alpha > 200 -> 255 (solidkan produk)
    arr = np.where(arr < 30, 0, arr)
    arr = np.where(arr > 200, 255, arr)
    alpha = Image.fromarray(arr.astype(np.uint8))

    # GENTLE erode (1px only, sebelumnya 3px)
    eroded = alpha.filter(ImageFilter.MinFilter(1))
    # GENTLE blur (0.8px, sebelumnya 2.5px)
    feathered = eroded.filter(ImageFilter.GaussianBlur(radius=0.8))
    rgba_image.putalpha(feathered)
    return rgba_image


if __name__ == "__main__":
    print("Object Isolator ready")

