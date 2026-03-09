"""
image_compositor.py
Isolates product from original photo, composites onto new backgrounds.

Features:
  - Background removal via rembg (AI-based) with PIL fallback
  - Composite product onto CF Stable Diffusion generated backgrounds
  - Add decorative elements: shadow, glow, badge, watermark
  - Generate 5 variations per product for multi-account use

Dependencies:
  - rembg (pip install rembg)
  - PIL/Pillow
  - cf_background_generator.py (CF Stable Diffusion backgrounds)
  - category_router.py
"""
import os
import sys
import random
import hashlib
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from engine.modules.category_router import get_category, get_accent_color

# CF SD generated backgrounds directory
CF_GENERATED_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'backgrounds', 'generated')
# Legacy photo backgrounds (fallback only)
PHOTO_BG_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'backgrounds', 'photo')


def get_random_background(category):
    """Get random background — prefer CF SD generated, fallback to photo dir."""
    # Priority 1: CF Stable Diffusion generated backgrounds
    cf_dir = os.path.join(CF_GENERATED_DIR, category)
    if os.path.exists(cf_dir):
        imgs = [f for f in os.listdir(cf_dir) if f.endswith(('.jpg', '.png', '.webp'))]
        if imgs:
            return os.path.join(cf_dir, random.choice(imgs))

    # Priority 2: Legacy photo backgrounds (backward compat)
    photo_dir = os.path.join(PHOTO_BG_DIR, category)
    if os.path.exists(photo_dir):
        imgs = [f for f in os.listdir(photo_dir) if f.endswith(('.jpg', '.png', '.webp'))]
        if imgs:
            return os.path.join(photo_dir, random.choice(imgs))

    return None

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  CONFIG
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
OUTPUT_SIZE = (1080, 1920)   # 9:16 vertical

# Position variations — subtle vertical shift for visual variety between scenes
PLACEMENT_PRESETS = [
    {'name': 'center',       'vy': 0.0},   # Centered
    {'name': 'center_high',  'vy': -0.04}, # Slightly up
    {'name': 'center_low',   'vy': 0.04},  # Slightly down
    {'name': 'up',           'vy': -0.06}, # More up
    {'name': 'down',         'vy': 0.06},  # More down
]

# Badge presets
BADGE_TEXTS = [
    "BEST SELLER", "TOP RATED", "PROMO", "NEW",
    "4.9", "VIRAL", "LIMITED", "SALE",
]


def composite_product_fullframe(img_path, placement, accent_color,
                                badge_text=None, channel_name=None):
    """Fill entire 9:16 frame with Shopee listing image. NO background removal.
    
    Simple approach that ALWAYS works:
    1. Load raw Shopee image (with original background — white, colored, anything)
    2. Scale to fill 100% of frame WIDTH (1080px)
    3. If image doesn't fill full height → extend edge colors up/down
    4. Result: ENTIRE frame covered. No dark gaps. No compositing.
    """
    W, H = OUTPUT_SIZE

    # Load raw image — NO background removal
    try:
        img = Image.open(img_path).convert('RGB')
    except Exception:
        img = Image.new('RGB', (W, W), (40, 40, 60))  # fallback

    iw, ih = img.size
    if iw == 0 or ih == 0:
        return Image.new('RGB', (W, H), (40, 40, 60))

    # === SCALE to fill full frame width ===
    scale = W / iw
    new_w = W
    new_h = int(ih * scale)
    img_scaled = img.resize((new_w, new_h), Image.LANCZOS)

    # === POSITION with subtle vertical shift ===
    vy_shift = placement.get('vy', 0.0)
    center_y = (H - new_h) // 2 + int(H * vy_shift)
    paste_y = max(0 - new_h + int(new_h * 0.2), min(center_y, H - int(new_h * 0.2)))

    # === CREATE FINAL CANVAS ===
    if new_h >= H:
        # Image is tall enough — just crop to frame
        crop_y = -paste_y if paste_y < 0 else 0
        paste_y_final = max(0, paste_y)
        canvas = Image.new('RGB', (W, H), (0, 0, 0))
        # Paste visible portion
        canvas.paste(img_scaled, (0, paste_y))
    else:
        # Image is shorter than frame — extend edges to fill
        canvas = _extend_to_fill(img_scaled, W, H, paste_y)

    # Add badge
    canvas_rgba = canvas.convert('RGBA')
    if badge_text:
        canvas_rgba = add_badge(canvas_rgba, badge_text, (W - 200, 40), accent_color)
    if channel_name:
        canvas_rgba = add_watermark(canvas_rgba, channel_name)

    return canvas_rgba.convert('RGB')


def _extend_to_fill(img_scaled, W, H, paste_y):
    """Extend image edges to fill entire frame when image is shorter than frame.
    Samples colors from top/bottom rows and creates smooth gradient extension.
    """
    new_w, new_h = img_scaled.size
    canvas = Image.new('RGB', (W, H), (30, 30, 35))
    draw = ImageDraw.Draw(canvas)
    img_data = np.array(img_scaled)

    # Sample colors from edges (average of top/bottom 5 pixel rows)
    sample_rows = min(5, new_h // 4)
    top_color = tuple(img_data[:sample_rows, :, :].mean(axis=(0, 1)).astype(int))
    bot_color = tuple(img_data[-sample_rows:, :, :].mean(axis=(0, 1)).astype(int))

    # Fill TOP area with gradient from darker → top_color
    top_gap = max(0, paste_y)
    if top_gap > 0:
        # Darken top edge slightly for vignette effect
        dark_top = tuple(max(0, c - 30) for c in top_color)
        for y in range(top_gap):
            t = y / max(top_gap, 1)
            r = int(dark_top[0] + (top_color[0] - dark_top[0]) * t)
            g = int(dark_top[1] + (top_color[1] - dark_top[1]) * t)
            b = int(dark_top[2] + (top_color[2] - dark_top[2]) * t)
            draw.line([(0, y), (W - 1, y)], fill=(r, g, b))

    # Paste actual image
    canvas.paste(img_scaled, (0, paste_y))

    # Fill BOTTOM area with gradient from bot_color → darker
    bot_start = paste_y + new_h
    bot_gap = H - bot_start
    if bot_gap > 0:
        dark_bot = tuple(max(0, c - 30) for c in bot_color)
        for y in range(bot_gap):
            t = y / max(bot_gap, 1)
            r = int(bot_color[0] + (dark_bot[0] - bot_color[0]) * t)
            g = int(bot_color[1] + (dark_bot[1] - bot_color[1]) * t)
            b = int(bot_color[2] + (dark_bot[2] - bot_color[2]) * t)
            draw.line([(0, bot_start + y), (W - 1, bot_start + y)], fill=(r, g, b))

    return canvas


def generate_variations(product_img_path, category, num_variations=5,
                        output_dir=None, produk_id='', channel_name=None):
    """Generate full-frame composites from Shopee image. NO background removal.
    
    1. Take raw Shopee image (whatever background it has)
    2. Scale to fill full frame width
    3. Extend edges to fill full frame height
    4. Each variation = slight vertical position shift
    
    Returns list of output file paths.
    """
    print(f"  Compositing {produk_id} ({category})...")

    if not os.path.exists(product_img_path):
        print(f"    [ERROR] Image not found: {product_img_path}")
        return []

    accent = get_accent_color(category)
    results = []

    for i in range(min(num_variations, len(PLACEMENT_PRESETS))):
        placement = PLACEMENT_PRESETS[i]
        badge = random.choice(BADGE_TEXTS) if random.random() > 0.5 else None

        composite = composite_product_fullframe(
            product_img_path, placement, accent,
            badge_text=badge, channel_name=channel_name
        )

        # Save — MUST match filename pattern generators expect!
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            filename = f"{produk_id}_composite_{i:03d}.png"
            filepath = os.path.join(output_dir, filename)
            composite.save(filepath, 'PNG', quality=92)
            results.append(filepath)
            print(f"    [OK] v{i+1}: {placement['name']} → {filename}")

    return results


def process_all_products(images_dir, output_dir, category='home', channel_name=None):
    """Process all product images in a directory."""
    print(f"=== Image Compositor: {category} ===")

    if not os.path.exists(images_dir):
        print(f"  Images dir not found: {images_dir}")
        return []

    images = [f for f in os.listdir(images_dir)
              if f.endswith(('.jpg', '.png', '.webp')) and 'composite' not in f]

    all_results = []
    for img_file in images:
        img_path = os.path.join(images_dir, img_file)
        produk_id = os.path.splitext(img_file)[0]

        results = generate_variations(
            img_path, category,
            num_variations=5,
            output_dir=output_dir,
            produk_id=produk_id,
            channel_name=channel_name
        )
        all_results.extend(results)

    print(f"\n  Total composites: {len(all_results)}")
    return all_results


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=str, default='engine/data/images',
                        help='Input images directory')
    parser.add_argument('--output', type=str, default='engine/data/composites',
                        help='Output composites directory')
    parser.add_argument('--category', type=str, default=None,
                        help='Override category for all images')
    parser.add_argument('--channel', type=str, default=None)
    args = parser.parse_args()

    # If category specified, use simple mode
    if args.category:
        process_all_products(args.input, args.output, args.category, args.channel)
    else:
        # Smart mode: read queue files to find products and their categories
        print("=== Image Compositor (Queue-Aware) ===")
        queue_files = [
            'engine/queue/yt_queue.jsonl',
            'engine/queue/tt_queue.jsonl',
            'engine/queue/fb_queue.jsonl',
        ]
        processed = set()
        total = 0

        for qf in queue_files:
            if not os.path.exists(qf):
                continue
            with open(qf, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    job = json.loads(line.strip())
                    produk_id = job.get('produk_id', '')
                    category = job.get('category', 'home')

                    if produk_id in processed:
                        continue
                    processed.add(produk_id)

                    # Find product image
                    img_path = None
                    for ext in ['jpg', 'png', 'webp']:
                        p = os.path.join(args.input, f"{produk_id}.{ext}")
                        if os.path.exists(p):
                            img_path = p
                            break

                    if not img_path:
                        print(f"  [SKIP] No image for {produk_id}")
                        continue

                    results = generate_variations(
                        img_path, category,
                        num_variations=5,
                        output_dir=args.output,
                        produk_id=produk_id,
                        channel_name=args.channel,
                    )
                    total += len(results)
                    print(f"  [OK] {produk_id} ({category}): {len(results)} composites")

        if total == 0 and not processed:
            print("  No queue files found, processing all images with default category")
            process_all_products(args.input, args.output, 'home', args.channel)
        else:
            print(f"\n  Total composites: {total}")

