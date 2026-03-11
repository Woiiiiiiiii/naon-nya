"""
premium_background.py
Premium gradient backgrounds for product videos.

Features:
  - Multi-stop gradient (3-4 colors, not plain 2-color)
  - Radial glow behind product center (spotlight effect)
  - Vignette (darker edges for cinematic look)
  - Category-themed palettes per channel

Used by all 4 video generators (yt_short, yt_long, tt, fb).
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ═══════════════════════════════════════════════════════════════════
#  PREMIUM COLOR PALETTES PER CATEGORY
#  Each palette: (gradient_top, gradient_mid, gradient_bot, glow_color)
# ═══════════════════════════════════════════════════════════════════
CATEGORY_PALETTES = {
    'fashion': {
        'name': 'Rose Blush',
        'gradients': [
            ((255, 200, 200), (255, 130, 160), (120, 40, 80), (255, 180, 200)),  # Rose
            ((250, 210, 190), (240, 150, 120), (100, 50, 60), (255, 200, 180)),  # Peach
            ((255, 190, 220), (200, 100, 140), (80, 30, 60),  (255, 170, 210)),  # Magenta
        ],
    },
    'gadget': {
        'name': 'Cyber Tech',
        'gradients': [
            ((30, 40, 80),   (20, 80, 130),  (10, 15, 30),  (0, 180, 255)),     # Navy-Cyan
            ((20, 30, 60),   (40, 60, 120),  (5, 10, 25),   (80, 160, 255)),    # Deep Blue
            ((25, 35, 70),   (10, 100, 100), (8, 12, 28),   (0, 220, 200)),     # Teal
        ],
    },
    'beauty': {
        'name': 'Soft Lavender',
        'gradients': [
            ((230, 200, 240), (180, 140, 200), (80, 50, 100), (220, 180, 240)),  # Lavender
            ((240, 210, 230), (200, 150, 180), (90, 50, 80),  (240, 200, 225)),  # Blush
            ((220, 190, 250), (160, 120, 210), (70, 40, 110), (210, 170, 250)),  # Purple
        ],
    },
    'home': {
        'name': 'Natural Warm',
        'gradients': [
            ((230, 220, 200), (180, 160, 120), (60, 50, 35),  (240, 220, 180)),  # Cream
            ((210, 225, 200), (140, 170, 120), (40, 50, 30),  (200, 230, 180)),  # Sage
            ((240, 215, 190), (200, 150, 100), (70, 45, 30),  (250, 210, 170)),  # Warm
        ],
    },
    'wellness': {
        'name': 'Ocean Zen',
        'gradients': [
            ((180, 230, 230), (80, 170, 180),  (20, 50, 60),  (140, 230, 230)),  # Mint
            ((190, 220, 240), (100, 160, 200), (25, 50, 70),  (160, 210, 250)),  # Sky
            ((170, 240, 210), (60, 180, 140),  (15, 50, 45),  (130, 240, 200)),  # Teal
        ],
    },
}

# TikTok: bold/vibrant
TT_PALETTES = [
    ((255, 50, 100),  (200, 30, 180),  (20, 10, 40),   (255, 80, 150)),   # Hot Pink
    ((80, 50, 200),   (150, 30, 255),  (15, 10, 35),   (140, 80, 255)),   # Purple Neon
    ((255, 80, 50),   (255, 150, 30),  (30, 15, 10),   (255, 120, 60)),   # Fire
]

# Facebook: professional/premium
FB_PALETTES = [
    ((40, 50, 100),   (30, 70, 140),   (10, 15, 30),   (60, 100, 200)),   # Navy
    ((50, 40, 90),    (40, 60, 130),   (12, 10, 25),   (80, 80, 180)),    # Indigo
    ((35, 55, 95),    (25, 80, 120),   (8, 12, 28),    (50, 120, 180)),   # Slate
]


def create_premium_background(width, height, category='home', variant=0, platform=None):
    """Create premium gradient background with glow + vignette.
    
    Args:
        width, height: canvas size
        category: product category for palette selection
        variant: index for palette rotation (0, 1, 2...)
        platform: 'tiktok' or 'facebook' for platform-specific palettes
    
    Returns: PIL Image (RGB)
    """
    # Select palette
    if platform == 'tiktok':
        palettes = TT_PALETTES
        pal = palettes[variant % len(palettes)]
    elif platform == 'facebook':
        palettes = FB_PALETTES
        pal = palettes[variant % len(palettes)]
    else:
        cat_data = CATEGORY_PALETTES.get(category, CATEGORY_PALETTES['home'])
        palettes = cat_data['gradients']
        pal = palettes[variant % len(palettes)]
    
    top, mid, bot, glow_color = pal
    
    # Step 1: Multi-stop gradient (top → mid → bottom)
    canvas = _multi_gradient(width, height, top, mid, bot)
    
    # Step 2: Radial glow behind product center
    _apply_radial_glow(canvas, width, height, glow_color, intensity=0.35)
    
    # Step 3: Vignette (darker edges)
    _apply_vignette(canvas, width, height, strength=0.4)
    
    return canvas


def _multi_gradient(w, h, top, mid, bot):
    """Create 3-stop vertical gradient: top → mid (40%) → bot."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    
    mid_point = int(h * 0.4)  # Mid color at 40% height
    
    for y in range(h):
        if y < mid_point:
            # Top → Mid
            r = y / max(mid_point, 1)
            color = tuple(int(top[c] * (1 - r) + mid[c] * r) for c in range(3))
        else:
            # Mid → Bottom
            r = (y - mid_point) / max(h - mid_point, 1)
            color = tuple(int(mid[c] * (1 - r) + bot[c] * r) for c in range(3))
        arr[y, :] = color
    
    return Image.fromarray(arr)


def _apply_radial_glow(canvas, w, h, glow_color, intensity=0.35):
    """Apply radial glow behind product center (spotlight effect)."""
    # Create glow mask (elliptical, centered, larger than product)
    glow = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    
    # Glow ellipse: centered, 60% of frame
    gw, gh = int(w * 0.6), int(h * 0.5)
    cx, cy = w // 2, int(h * 0.45)  # Slightly above center
    draw.ellipse(
        (cx - gw // 2, cy - gh // 2, cx + gw // 2, cy + gh // 2),
        fill=(*glow_color, int(255 * intensity))
    )
    
    # Blur for soft glow
    glow = glow.filter(ImageFilter.GaussianBlur(radius=min(w, h) // 6))
    
    # Composite glow onto canvas
    canvas_rgba = canvas.convert('RGBA')
    canvas_rgba = Image.alpha_composite(canvas_rgba, glow)
    canvas.paste(canvas_rgba.convert('RGB'))


def _apply_vignette(canvas, w, h, strength=0.4):
    """Apply vignette effect (darker edges for cinematic look)."""
    # Create dark overlay
    vignette = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(vignette)
    
    # Draw concentric ellipses from edge (dark) to center (transparent)
    steps = 20
    for i in range(steps):
        # Outer to inner
        progress = i / steps  # 0 (outer) → 1 (inner)
        alpha = int(255 * strength * (1 - progress) ** 2)  # Quadratic falloff
        
        # Shrink ellipse as we go inner
        margin_x = int(w * 0.05 * progress)
        margin_y = int(h * 0.05 * progress)
        
        if alpha > 0:
            draw.ellipse(
                (margin_x + i * w // (steps * 2),
                 margin_y + i * h // (steps * 2),
                 w - margin_x - i * w // (steps * 2),
                 h - margin_y - i * h // (steps * 2)),
                fill=(0, 0, 0, alpha)
            )
    
    # Blur for smooth vignette
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=min(w, h) // 8))
    
    canvas_rgba = canvas.convert('RGBA')
    canvas_rgba = Image.alpha_composite(canvas_rgba, vignette)
    canvas.paste(canvas_rgba.convert('RGB'))


def add_product_shadow(canvas, product_img, paste_x, paste_y):
    """Add soft shadow below product for floating 3D effect.
    
    Call BEFORE pasting the product image.
    """
    pw, ph = product_img.size
    
    # Create shadow (dark ellipse below product)
    shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    
    shadow_y = paste_y + ph - int(ph * 0.05)  # Just below product
    shadow_w = int(pw * 0.7)
    shadow_h = int(ph * 0.08)
    
    draw.ellipse(
        (paste_x + (pw - shadow_w) // 2, shadow_y,
         paste_x + (pw + shadow_w) // 2, shadow_y + shadow_h),
        fill=(0, 0, 0, 60)
    )
    
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=15))
    
    canvas_rgba = canvas.convert('RGBA')
    canvas_rgba = Image.alpha_composite(canvas_rgba, shadow)
    canvas.paste(canvas_rgba.convert('RGB'))


if __name__ == '__main__':
    # Test: generate sample backgrounds
    for cat in ['fashion', 'gadget', 'beauty', 'home', 'wellness']:
        bg = create_premium_background(1080, 1920, category=cat, variant=0)
        bg.save(f'/tmp/bg_{cat}.jpg', 'JPEG', quality=95)
        print(f"  {cat}: {CATEGORY_PALETTES[cat]['name']}")
    
    # TikTok & Facebook
    bg_tt = create_premium_background(1080, 1920, platform='tiktok', variant=0)
    bg_tt.save('/tmp/bg_tiktok.jpg', 'JPEG', quality=95)
    bg_fb = create_premium_background(1080, 1920, platform='facebook', variant=0)
    bg_fb.save('/tmp/bg_facebook.jpg', 'JPEG', quality=95)
    print("  tiktok: Bold Vibrant")
    print("  facebook: Professional Navy")
    print("\nAll backgrounds saved to /tmp/")
