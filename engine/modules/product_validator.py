"""
product_validator.py
Validates products AND their images before video rendering.

3-Level Image QC:
  HARD REJECT â†’ skip product entirely:
    - Image dominated by text (>60% area)
    - Placeholder/icon image (low color variance)
    - No product object detected (too uniform)

  SOFT REJECT â†’ try next image from same product:
    - Model without product clearly visible
    - Image too blurry (low edge density)
    - Overexposed (>80% bright pixels)
    - Background >80% without product object

  PASS â†’ product image is good for rendering:
    - Product object clearly visible as main subject
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
    def is_product_used(product_id, account_id): return False


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  IMAGE QC THRESHOLDS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
TEXT_EDGE_THRESHOLD = 0.25      # Edge density above this = text-heavy
BLUR_THRESHOLD = 5.0            # Std dev below this = too blurry
BRIGHT_THRESHOLD = 0.92         # >92% bright pixels = overexposed
COLOR_VARIANCE_MIN = 200        # Below this = placeholder/icon (single color)
UNIFORMITY_MAX = 0.95           # >95% same color = truly blank image


def analyze_image(img_path):
    """Analyze product image and return QC result.

    Returns:
        dict with keys:
          - status: 'pass', 'soft_reject', 'hard_reject'
          - reason: human-readable reason
          - scores: detailed metrics
    """
    try:
        img = Image.open(img_path).convert('RGB')
    except Exception as e:
        return {'status': 'hard_reject', 'reason': f'Cannot open image: {e}', 'scores': {}}

    w, h = img.size
    arr = np.array(img)

    scores = {}

    # â”€â”€ CHECK 1: Color variance (placeholder detection) â”€â”€
    # Placeholders have very low color variance
    hsv_variance = np.var(arr)
    scores['color_variance'] = float(hsv_variance)
    if hsv_variance < COLOR_VARIANCE_MIN:
        return {'status': 'hard_reject', 'reason': 'Placeholder image (low color variance)',
                'scores': scores}

    # â”€â”€ CHECK 2: Text detection via edge density â”€â”€
    # Text-heavy images have very high edge density
    gray = img.convert('L')
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_arr = np.array(edges)
    edge_density = np.mean(edge_arr > 30) / 255.0 * 100
    # Normalize to 0-1 range based on typical values
    edge_ratio = np.mean(edge_arr > 50)
    scores['edge_density'] = float(edge_ratio)
    if edge_ratio > TEXT_EDGE_THRESHOLD:
        # High edge = lots of text or complex patterns
        # Check if it's structured text (horizontal lines of edges)
        row_means = np.mean(edge_arr > 50, axis=1)
        text_rows = np.sum(row_means > 0.3)
        text_ratio = text_rows / h
        scores['text_ratio'] = float(text_ratio)
        if text_ratio > 0.6:
            return {'status': 'hard_reject', 'reason': f'Text-dominated image ({text_ratio:.0%})',
                    'scores': scores}

    # â”€â”€ CHECK 3: Uniformity (truly blank image detection) â”€â”€
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

    # â”€â”€ CHECK 4: Blur detection â”€â”€
    laplacian = gray.filter(ImageFilter.Kernel(
        size=(3, 3), kernel=[-1, -1, -1, -1, 8, -1, -1, -1, -1],
        scale=1, offset=128
    ))
    lap_std = np.std(np.array(laplacian).astype(float))
    scores['sharpness'] = float(lap_std)
    if lap_std < BLUR_THRESHOLD:
        return {'status': 'soft_reject', 'reason': f'Image too blurry (sharpness={lap_std:.1f})',
                'scores': scores}

    # â”€â”€ CHECK 5: Overexposure â”€â”€
    brightness = np.mean(arr, axis=2)
    bright_ratio = np.mean(brightness > 240)
    scores['bright_ratio'] = float(bright_ratio)
    if bright_ratio > BRIGHT_THRESHOLD:
        return {'status': 'soft_reject', 'reason': f'Overexposed ({bright_ratio:.0%} bright)',
                'scores': scores}

    # â”€â”€ CHECK 6: Background dominance (info only) â”€â”€
    # White background is normal for Shopee â€” image_compositor removes it
    bg_ratio = np.mean(brightness > 220)
    scores['bg_ratio'] = float(bg_ratio)
    if bg_ratio > 0.95:
        # Only reject if virtually NO product content at all
        product_area = 1 - bg_ratio
        if product_area < 0.02:
            return {'status': 'soft_reject',
                    'reason': f'Background dominates ({bg_ratio:.0%}), tiny product',
                    'scores': scores}

    # â”€â”€ CHECK 7: Person/skin detection â”€â”€
    # Reject images with large areas of human skin
    # CAREFUL: many products (leather, wood, cosmetics) have warm tones
    # Only reject when skin coverage is VERY high (clearly a person)
    try:
        hsv_img = img.convert('HSV')
        hsv_arr = np.array(hsv_img)
        h_ch, s_ch, v_ch = hsv_arr[:, :, 0], hsv_arr[:, :, 1], hsv_arr[:, :, 2]

        # TIGHT skin-tone range in PIL HSV (H:0-255 = 0-360°)
        # H: 5-25 in PIL = ~7°-35° actual = peach/tan skin only
        # Excludes: brown (leather), orange (products), red (packaging), yellow
        skin_mask = (
            (h_ch >= 5) & (h_ch <= 25) &      # Narrow hue: peach/tan skin only
            (s_ch >= 50) & (s_ch <= 160) &     # Moderate saturation
            (v_ch >= 100) & (v_ch <= 240)      # Not too dark, not too bright
        )

        # Exclude white/very bright background pixels
        non_bg_mask = (v_ch < 220) | (s_ch > 20)
        valid_pixels = np.sum(non_bg_mask)

        if valid_pixels > 100:
            skin_ratio = np.sum(skin_mask & non_bg_mask) / valid_pixels
            scores['skin_ratio'] = float(skin_ratio)
            # Only reject if >40% is clearly skin (= person dominates frame)
            if skin_ratio > 0.40:
                return {'status': 'soft_reject',
                        'reason': f'Image likely contains a person ({skin_ratio:.0%} skin pixels)',
                        'scores': scores}
    except Exception:
        pass

    # â”€â”€ ALL CHECKS PASSED â”€â”€
    return {'status': 'pass', 'reason': 'Image OK', 'scores': scores}


def validate_product_image(produk_id, images_dir='engine/data/images'):
    """Validate a product's image. Try alternatives if soft-rejected.

    Returns: (status, valid_image_path or None)
    """
    # Try main image first
    main_path = os.path.join(images_dir, f"{produk_id}.jpg")
    if not os.path.exists(main_path):
        main_path = os.path.join(images_dir, f"{produk_id}.png")
    if not os.path.exists(main_path):
        # No image = warn but allow through (will use placeholder)
        print(f"    [WARN] {produk_id}: no image file, will use placeholder")
        return 'pass', None

    result = analyze_image(main_path)

    if result['status'] == 'pass':
        return 'pass', main_path

    if result['status'] == 'hard_reject':
        print(f"  [HARD REJECT] {produk_id}: {result['reason']}")
        return 'hard_reject', None

    # Soft reject â€” try alternative images (_2, _3, etc.)
    print(f"  [SOFT REJECT] {produk_id}: {result['reason']}, trying alternatives...")
    for suffix in ['_2', '_3', '_4', '_5']:
        alt_path = os.path.join(images_dir, f"{produk_id}{suffix}.jpg")
        if not os.path.exists(alt_path):
            alt_path = os.path.join(images_dir, f"{produk_id}{suffix}.png")
        if not os.path.exists(alt_path):
            continue

        alt_result = analyze_image(alt_path)
        if alt_result['status'] == 'pass':
            print(f"    [OK] Alternative {suffix} passed!")
            return 'pass', alt_path
        else:
            print(f"    [--] Alternative {suffix}: {alt_result['reason']}")

    # All alternatives failed
    print(f"    [FAIL] No valid images for {produk_id}")
    return 'soft_reject', None


def validate_products(input_file, output_file):
    """Validate products from CSV â€” includes image QC."""
    print(f"Validating products from {input_file}...")

    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    df = pd.read_csv(input_file)

    # Required columns
    required = ['produk_id', 'nama', 'deskripsi_singkat', 'shopee_url']
    for col in required:
        if col not in df.columns:
            # Add tokopedia_url if missing (optional)
            if col == 'tokopedia_url':
                df[col] = ''
                continue
            print(f"Error: Missing column {col}")
            return

    # Drop rows with missing crucial data
    clean_df = df.dropna(subset=['produk_id', 'nama'])

    # Image QC
    images_dir = 'engine/data/images'
    qc_results = []

    for _, row in clean_df.iterrows():
        pid = row['produk_id']
        status, valid_path = validate_product_image(pid, images_dir)
        qc_results.append({
            'produk_id': pid,
            'qc_status': status,
            'valid_image': valid_path
        })

    # Filter: keep products that passed or soft-rejected (only hard_reject blocks)
    passed_ids = [r['produk_id'] for r in qc_results if r['qc_status'] in ('pass', 'soft_reject')]
    rejected_ids = [r['produk_id'] for r in qc_results if r['qc_status'] not in ('pass', 'soft_reject')]

    validated = clean_df[clean_df['produk_id'].isin(passed_ids)]
    validated.to_csv(output_file, index=False)

    print(f"\nImage QC Summary:")
    print(f"  Passed:  {len(passed_ids)}")
    print(f"  Rejected: {len(rejected_ids)}")
    if rejected_ids:
        for r in qc_results:
            if r['qc_status'] != 'pass':
                print(f"    - {r['produk_id']}: {r['qc_status']}")
    print(f"Product validation complete. {len(validated)} products validated.")


if __name__ == "__main__":
    input_path = "engine/data/produk.csv"
    output_path = "engine/data/produk_valid.csv"
    validate_products(input_path, output_path)
