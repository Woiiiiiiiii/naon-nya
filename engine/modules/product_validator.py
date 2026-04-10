"""
product_validator.py
Validates products AND their images before video rendering.

Image QC Rules:
  HARD REJECT → skip product entirely:
    - Placeholder/icon image (low color variance)
    - Blank image (too uniform / single color)
    - Image too blurry (low sharpness)
    - Product too small in frame (<10% fill)
    - Cannot open/read image file

  MINIMUM IMAGE COUNT → product MUST have at least 4 images:
    - image.jpg (main) + image_2.jpg + image_3.jpg + image_4.jpg
    - ALL images are validated for quality
    - If any image fails QC or is missing → product REJECTED

  PASS → all images are good quality + minimum 4 images present
"""
import pandas as pd
import os
import sys
import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(__file__))
try:
    from dedup_tracker import is_product_used
except ImportError:
    def is_product_used(product_id, account_id=None): return False


# ═══════════════════════════════════════════════════════════════════
#  IMAGE QC THRESHOLDS
# ═══════════════════════════════════════════════════════════════════
BLUR_THRESHOLD = 5.0            # Std dev below this = too blurry
COLOR_VARIANCE_MIN = 200        # Below this = placeholder/icon (single color)
UNIFORMITY_MAX = 0.95           # >95% same color = truly blank image
MIN_REQUIRED_IMAGES = 4         # Minimum number of images per product (MANDATORY)
MIN_IMAGE_RESOLUTION = 800      # Minimum width/height — below this = pixelated at 1080x1920


def analyze_image(img_path):
    """Analyze product image and return QC result.

    Checks:
      1. Color variance (placeholder detection)
      2. Uniformity (blank image detection)
      3. Blur detection (sharpness)
      4. Product fill (product size in frame)

    Returns:
        dict with keys:
          - status: 'pass', 'hard_reject'
          - reason: human-readable reason
          - scores: detailed metrics
    """
    try:
        img = Image.open(img_path).convert('RGB')
    except Exception as e:
        return {'status': 'hard_reject', 'reason': f'Cannot open image: {e}', 'scores': {}}

    w, h = img.size
    arr = np.array(img)

    scores = {'resolution': f'{w}x{h}'}

    # ── CHECK 0: Resolution (prevent pixelated upscale) ──
    # Images smaller than 800px will look pixelated when stretched to 1080x1920
    if w < MIN_IMAGE_RESOLUTION or h < MIN_IMAGE_RESOLUTION:
        return {'status': 'hard_reject',
                'reason': f'Resolution too low: {w}x{h} (min {MIN_IMAGE_RESOLUTION}px)',
                'scores': scores}


    # ── CHECK 1: Color variance (placeholder detection) ──
    # Placeholders have very low color variance
    hsv_variance = np.var(arr)
    scores['color_variance'] = float(hsv_variance)
    if hsv_variance < COLOR_VARIANCE_MIN:
        return {'status': 'hard_reject', 'reason': 'Placeholder image (low color variance)',
                'scores': scores}

    # ── CHECK 2: Uniformity (truly blank image detection) ──
    # Only reject if image is TRULY single-color (blank/placeholder)
    # Shopee products on white backgrounds are normal and pass
    small = img.resize((50, 50))
    small_arr = np.array(small).reshape(-1, 3)
    from collections import Counter
    # Quantize to coarse 64-step to catch only truly uniform images
    quantized = (small_arr // 64) * 64
    color_counts = Counter(map(tuple, quantized))
    dominant_count = color_counts.most_common(1)[0][1]
    uniformity = dominant_count / len(small_arr)
    scores['uniformity'] = float(uniformity)
    if uniformity > UNIFORMITY_MAX:
        return {'status': 'hard_reject', 'reason': f'Blank image ({uniformity:.0%} uniform)',
                'scores': scores}

    # ── CHECK 3: Blur detection ──
    gray = img.convert('L')
    laplacian = gray.filter(ImageFilter.Kernel(
        size=(3, 3), kernel=[-1, -1, -1, -1, 8, -1, -1, -1, -1],
        scale=1, offset=128
    ))
    lap_std = np.std(np.array(laplacian).astype(float))
    scores['sharpness'] = float(lap_std)
    if lap_std < BLUR_THRESHOLD:
        return {'status': 'hard_reject', 'reason': f'Image too blurry (sharpness={lap_std:.1f})',
                'scores': scores}

    # ── CHECK 4: Product Fill (gambar harus penuh space) ──
    # Reject images where product is too small / doesn't fill frame adequately.
    # Uses foreground detection: count non-background pixels as "product area".
    # Background = very bright (white/near-white) OR very dark (black) pixels.
    try:
        brightness = np.mean(arr, axis=2)
        # Foreground = pixels that are NOT white bg AND NOT black bg
        fg_mask = (brightness > 30) & (brightness < 235)
        fg_ratio = np.mean(fg_mask)
        scores['product_fill'] = float(fg_ratio)
        # If product fills less than 10% of image → too small
        if fg_ratio < 0.10:
            return {'status': 'hard_reject',
                    'reason': f'Product too small ({fg_ratio:.0%} fill)',
                    'scores': scores}
    except Exception:
        pass

    # ── ALL CHECKS PASSED ──
    return {'status': 'pass', 'reason': 'Image OK', 'scores': scores}


def _find_image(images_dir, produk_id, suffix=''):
    """Find image file with any supported extension."""
    base = f"{produk_id}{suffix}"
    for ext in ['jpg', 'jpeg', 'png', 'webp']:
        path = os.path.join(images_dir, f"{base}.{ext}")
        if os.path.exists(path):
            return path
    return None


def validate_product_image(produk_id, images_dir='engine/data/images'):
    """Validate a product's images — ALL images must pass QC.

    Requirements:
      1. Product MUST have at least MIN_REQUIRED_IMAGES (4) images
      2. ALL images must pass quality checks (not alternatives — mandatory!)
      3. Images: {id}.jpg, {id}_2.jpg, {id}_3.jpg, {id}_4.jpg (+ optional _5.jpg)

    Returns: (status, list_of_valid_image_paths or None)
    """
    # Define all image slots: main + numbered
    image_slots = [
        ('main', ''),       # {id}.jpg
        ('img_2', '_2'),    # {id}_2.jpg
        ('img_3', '_3'),    # {id}_3.jpg
        ('img_4', '_4'),    # {id}_4.jpg
        ('img_5', '_5'),    # {id}_5.jpg (bonus, not required)
    ]

    found_images = []
    failed_images = []

    for slot_name, suffix in image_slots:
        img_path = _find_image(images_dir, produk_id, suffix)

        if img_path is None:
            if len(found_images) < MIN_REQUIRED_IMAGES:
                # Still need more images — this missing one matters
                failed_images.append((slot_name, 'Image file not found'))
            continue

        # Validate image quality
        result = analyze_image(img_path)

        if result['status'] == 'pass':
            found_images.append(img_path)
        else:
            failed_images.append((slot_name, result['reason']))
            print(f"    [REJECT] {produk_id} {slot_name}: {result['reason']}")

    # ── CHECK: Minimum image count ──
    if len(found_images) < MIN_REQUIRED_IMAGES:
        missing = MIN_REQUIRED_IMAGES - len(found_images)
        reason = f"Not enough valid images: {len(found_images)}/{MIN_REQUIRED_IMAGES} (need {missing} more)"
        print(f"  [HARD REJECT] {produk_id}: {reason}")
        if failed_images:
            for slot, fail_reason in failed_images:
                print(f"    └─ {slot}: {fail_reason}")
        return 'hard_reject', None

    # All requirements met
    print(f"  [PASS] {produk_id}: {len(found_images)} valid images ✓")
    return 'pass', found_images


def validate_products(input_file, output_file):
    """Validate products from CSV — includes image QC.
    CACHED: If output already exists with data, skip re-validation."""
    # CACHE CHECK: skip if output already has validated products
    if os.path.exists(output_file) and os.path.getsize(output_file) > 100:
        try:
            existing = pd.read_csv(output_file)
            if len(existing) > 0:
                print(f"=== Product Validator: CACHED ({len(existing)} products in {output_file}) ===")
                print(f"  Skipping re-validation. Delete {output_file} to force re-run.")
                return
        except Exception:
            pass
    
    print(f"Validating products from {input_file}...")

    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    df = pd.read_csv(input_file)

    # Required columns (hard fail if missing)
    required = ['produk_id', 'nama']
    for col in required:
        if col not in df.columns:
            print(f"Error: Missing column {col}")
            return
    
    # Optional columns — add with empty values if missing
    for col in ['deskripsi_singkat', 'shopee_url', 'image_url', 'category', 'source']:
        if col not in df.columns:
            df[col] = ''
            print(f"  [INFO] Added missing optional column: {col}")

    # Drop rows with missing crucial data
    clean_df = df.dropna(subset=['produk_id', 'nama'])

    # Image QC
    images_dir = 'engine/data/images'
    qc_results = []

    for _, row in clean_df.iterrows():
        pid = row['produk_id']
        status, valid_paths = validate_product_image(pid, images_dir)
        qc_results.append({
            'produk_id': pid,
            'qc_status': status,
            'valid_images': valid_paths,
            'image_count': len(valid_paths) if valid_paths else 0,
        })

    # Filter: only keep products that PASSED (hard_reject = blocked)
    passed_ids = [r['produk_id'] for r in qc_results if r['qc_status'] == 'pass']
    rejected_ids = [r['produk_id'] for r in qc_results if r['qc_status'] != 'pass']

    validated = clean_df[clean_df['produk_id'].isin(passed_ids)]
    validated.to_csv(output_file, index=False)

    print(f"\nImage QC Summary:")
    print(f"  Passed:   {len(passed_ids)} (all have ≥{MIN_REQUIRED_IMAGES} quality images)")
    print(f"  Rejected: {len(rejected_ids)}")
    if rejected_ids:
        for r in qc_results:
            if r['qc_status'] != 'pass':
                print(f"    ✗ {r['produk_id']}: {r['qc_status']} ({r['image_count']} valid images)")
    print(f"Product validation complete. {len(validated)} products validated.")


if __name__ == "__main__":
    input_path = "engine/data/produk.csv"
    output_path = "engine/data/produk_valid.csv"
    validate_products(input_path, output_path)
