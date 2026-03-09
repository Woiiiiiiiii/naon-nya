"""
depth_analyzer.py
Analyze background depth using MiDaS via Hugging Face Inference API.
Generates depth maps for natural product placement and parallax effects.
Falls back to simple brightness-based estimation if API unavailable.
"""
import os
import json
import requests
import numpy as np
from PIL import Image, ImageFilter
from io import BytesIO

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'depth_maps')

HF_MODEL = "Intel/dpt-large"
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


def analyze_depth_hf(image_path, account_id='yt_1'):
    """Get depth map from MiDaS via HF API."""
    api_key = _get_hf_key(account_id)
    if not api_key:
        return estimate_depth_local(image_path)

    try:
        with open(image_path, 'rb') as f:
            data = f.read()

        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.post(HF_API_URL, headers=headers, data=data, timeout=60)

        if resp.status_code == 200:
            depth_img = Image.open(BytesIO(resp.content)).convert('L')
            return np.array(depth_img)
        else:
            print(f"  [WARN] Depth API {resp.status_code}")
            return estimate_depth_local(image_path)
    except Exception as e:
        print(f"  [WARN] Depth analysis failed: {e}")
        return estimate_depth_local(image_path)


def estimate_depth_local(image_path):
    """Local depth estimation using brightness gradient as proxy."""
    img = Image.open(image_path).convert('L')
    img = img.filter(ImageFilter.GaussianBlur(radius=10))
    arr = np.array(img)
    # Assume brighter areas = closer (simplified)
    return arr


def find_best_placement(depth_map, product_size, canvas_size=(1080, 1920)):
    """Find the best position for product placement based on depth map.
    
    Returns (x, y) position where product should be placed for natural look.
    Prefers foreground areas (high depth values) with enough empty space.
    """
    h, w = depth_map.shape
    ph, pw = product_size

    # Resize depth map to canvas size
    depth_resized = np.array(
        Image.fromarray(depth_map).resize((canvas_size[0], canvas_size[1]), Image.LANCZOS)
    )

    # Define candidate regions (avoid extreme edges)
    margin_x = int(canvas_size[0] * 0.1)
    margin_y = int(canvas_size[1] * 0.15)

    # Candidate positions: center, left-center, right-center, lower-center
    candidates = [
        ((canvas_size[0] - pw) // 2, int(canvas_size[1] * 0.25)),         # Upper center
        ((canvas_size[0] - pw) // 2, int(canvas_size[1] * 0.35)),         # Center
        (margin_x, int(canvas_size[1] * 0.30)),                           # Left
        (canvas_size[0] - pw - margin_x, int(canvas_size[1] * 0.30)),     # Right
        ((canvas_size[0] - pw) // 2, int(canvas_size[1] * 0.20)),         # High center
    ]

    best_pos = candidates[0]
    best_score = -1

    for cx, cy in candidates:
        if cx < 0 or cy < 0 or cx + pw > canvas_size[0] or cy + ph > canvas_size[1]:
            continue

        # Score based on average depth in the product region
        region = depth_resized[cy:min(cy + ph, canvas_size[1]),
                               cx:min(cx + pw, canvas_size[0])]
        if region.size == 0:
            continue

        # Prefer foreground (higher depth) and uniform areas
        avg_depth = np.mean(region)
        uniformity = 1.0 / (np.std(region) + 1)
        score = avg_depth * 0.6 + uniformity * 100 * 0.4

        if score > best_score:
            best_score = score
            best_pos = (cx, cy)

    return best_pos


def get_parallax_offset(depth_map, t, intensity=15):
    """Calculate parallax offset based on depth map and time.
    
    Returns (x_offset, y_offset) arrays for foreground and background layers.
    Foreground moves more than background for 3D feel.
    """
    h, w = depth_map.shape
    norm_depth = depth_map.astype(np.float32) / 255.0

    # Oscillating motion
    import math
    x_base = math.sin(t * 0.5) * intensity
    y_base = math.cos(t * 0.3) * intensity * 0.5

    # Foreground moves more than background
    fg_offset = (int(x_base * 1.5), int(y_base * 1.5))
    bg_offset = (int(x_base * 0.3), int(y_base * 0.3))

    return fg_offset, bg_offset


if __name__ == "__main__":
    os.makedirs(CACHE_DIR, exist_ok=True)
    print("Depth Analyzer ready")
    # Test with a sample image if available
    test_img = "engine/data/images/test.jpg"
    if os.path.exists(test_img):
        depth = estimate_depth_local(test_img)
        print(f"Depth map shape: {depth.shape}")
        pos = find_best_placement(depth, (400, 400))
        print(f"Best placement: {pos}")
