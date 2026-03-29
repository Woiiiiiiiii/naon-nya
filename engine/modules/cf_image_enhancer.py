"""
cf_image_enhancer.py
Enhance & beautify product composite images.

ROLE: Image quality enhancer
1. Enhance ALL composite images before video creation
2. Sharpen product details, improve contrast, clean up edges
3. Professional-grade local processing (no external API needed)

NOTE: CF SD XL Base model does NOT support img2img.
      All enhancement is done locally via PIL for reliability.
"""

import os
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
from io import BytesIO

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
TARGET_SIZE = (1080, 1920)  # 9:16 vertical

# Per-category enhancement presets
CATEGORY_ENHANCE = {
    'fashion':  {'contrast': 1.12, 'color': 1.15, 'sharp': 1.4, 'brightness': 1.02},
    'gadget':   {'contrast': 1.18, 'color': 1.05, 'sharp': 1.5, 'brightness': 1.00},
    'beauty':   {'contrast': 1.08, 'color': 1.12, 'sharp': 1.3, 'brightness': 1.05},
    'home':     {'contrast': 1.10, 'color': 1.10, 'sharp': 1.3, 'brightness': 1.03},
    'wellness': {'contrast': 1.12, 'color': 1.08, 'sharp': 1.35, 'brightness': 1.02},
}
DEFAULT_ENHANCE = {'contrast': 1.12, 'color': 1.10, 'sharp': 1.35, 'brightness': 1.02}





def enhance_local(img_path, category='home'):
    """Professional-grade local image enhancement.
    
    Applied to ALL composite images — fast, free, always works:
    1. Auto-levels: normalize brightness range
    2. Category-tuned contrast, color, sharpness
    3. Adaptive brightness correction
    4. Edge-aware sharpening (unsharp mask)
    5. Highlight recovery (prevent blown-out whites)
    
    Returns: enhanced PIL Image (RGB)
    """
    try:
        img = Image.open(img_path).convert('RGB')
    except Exception:
        return None

    preset = CATEGORY_ENHANCE.get(category, DEFAULT_ENHANCE)
    data = np.array(img, dtype=np.float32)

    # 1. Auto-levels — stretch histogram to use full range
    for ch in range(3):
        ch_data = data[:, :, ch]
        lo = np.percentile(ch_data, 1)
        hi = np.percentile(ch_data, 99)
        if hi - lo > 10:
            data[:, :, ch] = np.clip((ch_data - lo) * 255.0 / (hi - lo), 0, 255)
    img = Image.fromarray(data.astype(np.uint8))

    # 2. Adaptive brightness — correct if too dark or bright
    avg_brightness = data.mean()
    if avg_brightness < 90:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.25)
    elif avg_brightness < 110:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(preset['brightness'])
    elif avg_brightness > 220:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(0.92)

    # 3. Contrast — category-tuned
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(preset['contrast'])

    # 4. Color vibrancy — category-tuned
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(preset['color'])

    # 5. Sharpness — category-tuned + unsharp mask for edge clarity
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(preset['sharp'])
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=100, threshold=3))

    # 6. Highlight recovery — prevent blown-out whites
    data = np.array(img, dtype=np.float32)
    mask = data > 245
    if mask.any():
        data[mask] = 245 - (data[mask] - 245) * 0.5
        img = Image.fromarray(np.clip(data, 0, 255).astype(np.uint8))

    print(f"    [ENHANCE] {category}: auto-levels+contrast+color+sharp applied")
    return img


def enhance_composite(img_path, category='home', account_index=None):
    """Full enhancement pipeline for a composite image.
    Uses local PIL processing only (professional quality, no external API).
    
    Returns: True if enhanced, False if failed
    """
    enhanced = enhance_local(img_path, category)
    if enhanced is None:
        print(f"    [ENHANCE] Failed to load: {img_path}")
        return False

    enhanced.save(img_path, 'PNG', quality=95)
    print(f"    [ENHANCE] Enhanced → {os.path.basename(img_path)}")
    return True


def _load_product_category_map():
    """Load product_id → category mapping from produk.csv."""
    import csv
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'produk.csv')
    mapping = {}
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row.get('produk_id', '')
                cat = row.get('category', '')
                if pid and cat:
                    mapping[pid] = cat
    return mapping


def _load_queued_product_ids():
    """Load product IDs from queue files — ONLY these need enhancing."""
    queued = set()
    queue_files = [
        os.path.join(os.path.dirname(__file__), '..', 'queue', 'yt_queue.jsonl'),
        os.path.join(os.path.dirname(__file__), '..', 'queue', 'tt_queue.jsonl'),
        os.path.join(os.path.dirname(__file__), '..', 'queue', 'fb_queue.jsonl'),
    ]
    for qf in queue_files:
        if os.path.exists(qf):
            with open(qf, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            job = json.loads(line)
                            pid = job.get('produk_id', '')
                            if pid:
                                queued.add(pid)
                        except Exception:
                            pass
    return queued


def enhance_all_composites(composites_dir, category=None, account_index=None):
    """Enhance composite images — ONLY for products in the queue.
    Uses professional-grade local processing (no external API needed).
    """
    if not os.path.exists(composites_dir):
        print(f"  [ENHANCE] Dir not found: {composites_dir}")
        return

    all_files = [f for f in os.listdir(composites_dir) 
                 if f.endswith('.png') and 'composite' in f]
    
    if not all_files:
        print(f"  [ENHANCE] No composites found in {composites_dir}")
        return

    # QUEUE FILTER: only enhance products that are actually queued for video
    queued_ids = _load_queued_product_ids()
    if queued_ids:
        files = []
        for f in all_files:
            pid = f.split('_composite_')[0] if '_composite_' in f else f.replace('.png', '')
            if pid in queued_ids:
                files.append(f)
        print(f"  [ENHANCE] Queue filter: {len(files)}/{len(all_files)} composites "
              f"(only {len(queued_ids)} queued products)")
    else:
        files = all_files
        print(f"  [ENHANCE] No queue found — enhancing all {len(files)} composites")

    if not files:
        print(f"  [ENHANCE] No composites match queued products — skipping")
        return

    # Load product→category map for per-image category routing
    prod_cat_map = _load_product_category_map()
    print(f"  [ENHANCE] Enhancing {len(files)} composites (local pro-grade)...")

    enhanced_count = 0
    for f in files:
        fpath = os.path.join(composites_dir, f)
        pid = f.split('_composite_')[0] if '_composite_' in f else f.replace('.png', '')
        img_cat = category or prod_cat_map.get(pid, 'home')

        if enhance_composite(fpath, img_cat):
            enhanced_count += 1

    print(f"  [ENHANCE] Done — {enhanced_count}/{len(files)} images enhanced")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=str, required=True, help='Composites directory')
    parser.add_argument('--category', type=str, default=None)
    parser.add_argument('--account', type=int, default=None)
    args = parser.parse_args()

    enhance_all_composites(args.input, args.category, args.account)
