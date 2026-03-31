"""
slideshow_frame.py
Decorative frame (pigura) + running lights for product slideshow videos.

Features:
  - Category-themed frame colors
  - Animated running lights (chase, twinkle, pulse, rainbow)
  - Vignette effect
  - Soft glow behind frame
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import math
import random as _random


# ═══════════════════════════════════════════════════════════════════
#  Frame color themes per category
# ═══════════════════════════════════════════════════════════════════
FRAME_THEMES = {
    'fashion': {
        'frame_color': (200, 150, 130),        # Rose gold
        'light_color': (255, 180, 200),         # Pink lights
        'glow_color': (255, 120, 180, 60),      # Pink glow
        'inner_color': (180, 130, 110),         # Darker rose
    },
    'gadget': {
        'frame_color': (60, 140, 220),          # Neon blue
        'light_color': (100, 220, 255),         # Cyan lights
        'glow_color': (0, 180, 255, 60),        # Cyan glow
        'inner_color': (40, 100, 180),          # Darker blue
    },
    'beauty': {
        'frame_color': (210, 180, 120),         # Soft gold
        'light_color': (255, 240, 200),         # Warm white lights
        'glow_color': (255, 200, 150, 60),      # Gold glow
        'inner_color': (180, 150, 90),          # Darker gold
    },
    'home': {
        'frame_color': (160, 120, 80),          # Wood tone
        'light_color': (255, 220, 150),         # Warm yellow lights
        'glow_color': (255, 180, 100, 60),      # Warm glow
        'inner_color': (130, 90, 60),           # Darker wood
    },
    'wellness': {
        'frame_color': (80, 160, 100),          # Fresh green
        'light_color': (150, 255, 200),         # Mint lights
        'glow_color': (100, 220, 150, 60),      # Green glow
        'inner_color': (60, 130, 80),           # Darker green
    },
}


# ═══════════════════════════════════════════════════════════════════
#  Running light patterns
# ═══════════════════════════════════════════════════════════════════
def _get_light_positions(w, h, margin, num_lights=24):
    """Calculate positions for lights along the frame perimeter."""
    positions = []
    # Perimeter path: top → right → bottom → left
    inner_x1, inner_y1 = margin, margin
    inner_x2, inner_y2 = w - margin, h - margin

    perimeter = 2 * (inner_x2 - inner_x1) + 2 * (inner_y2 - inner_y1)
    step = perimeter / num_lights

    # Top edge (left to right)
    x, y = inner_x1, inner_y1
    dist = 0
    while dist < (inner_x2 - inner_x1) and len(positions) < num_lights:
        positions.append((int(x), int(y)))
        x += step
        dist += step
        if x >= inner_x2:
            break

    # Right edge (top to bottom)
    x = inner_x2
    y = inner_y1
    dist = 0
    while dist < (inner_y2 - inner_y1) and len(positions) < num_lights:
        positions.append((int(x), int(y)))
        y += step
        dist += step
        if y >= inner_y2:
            break

    # Bottom edge (right to left)
    x = inner_x2
    y = inner_y2
    dist = 0
    while dist < (inner_x2 - inner_x1) and len(positions) < num_lights:
        positions.append((int(x), int(y)))
        x -= step
        dist += step
        if x <= inner_x1:
            break

    # Left edge (bottom to top)
    x = inner_x1
    y = inner_y2
    dist = 0
    while dist < (inner_y2 - inner_y1) and len(positions) < num_lights:
        positions.append((int(x), int(y)))
        y -= step
        dist += step
        if y <= inner_y1:
            break

    # Re-distribute evenly if we didn't get enough
    if len(positions) < num_lights:
        positions = []
        total_p = 2 * (inner_x2 - inner_x1 + inner_y2 - inner_y1)
        seg = total_p / num_lights
        for i in range(num_lights):
            d = i * seg
            if d < (inner_x2 - inner_x1):
                positions.append((int(inner_x1 + d), inner_y1))
            elif d < (inner_x2 - inner_x1) + (inner_y2 - inner_y1):
                dd = d - (inner_x2 - inner_x1)
                positions.append((inner_x2, int(inner_y1 + dd)))
            elif d < 2 * (inner_x2 - inner_x1) + (inner_y2 - inner_y1):
                dd = d - (inner_x2 - inner_x1) - (inner_y2 - inner_y1)
                positions.append((int(inner_x2 - dd), inner_y2))
            else:
                dd = d - 2 * (inner_x2 - inner_x1) - (inner_y2 - inner_y1)
                positions.append((inner_x1, int(inner_y2 - dd)))

    return positions


def _chase_brightness(light_index, num_lights, t, speed=3.0):
    """Chase pattern: bright dot moves clockwise."""
    phase = (t * speed - light_index / num_lights) % 1.0
    # Gaussian-like brightness falloff
    b = math.exp(-((phase - 0.5) ** 2) / 0.02)
    # Also a base brightness so lights aren't fully off
    return max(0.15, min(1.0, b * 0.85 + 0.15))


def _twinkle_brightness(light_index, num_lights, t, seed=42):
    """Twinkle: random independent blinking."""
    phase = math.sin(t * 4.0 + light_index * 1.7 + seed * 0.3) * 0.5 + 0.5
    return max(0.1, phase)


def _pulse_brightness(light_index, num_lights, t):
    """Pulse: all lights breathe together."""
    b = math.sin(t * 2.5) * 0.4 + 0.6
    return max(0.2, b)


def _rainbow_brightness(light_index, num_lights, t):
    """Rainbow wave: always bright, color shifts (handled separately)."""
    return 0.9


def _rainbow_color(light_index, num_lights, t, base_color):
    """Get rainbow-shifted color for a light."""
    hue_offset = (light_index / num_lights + t * 0.3) % 1.0
    # Simple HSV-like hue rotation on the base color
    r, g, b = base_color
    shift = int(hue_offset * 360) % 360
    if shift < 120:
        f = shift / 120.0
        return (int(r * (1 - f) + g * f), int(g * f + b * (1 - f)), int(b * (1 - f)))
    elif shift < 240:
        f = (shift - 120) / 120.0
        return (int(g * (1 - f)), int(g * (1 - f) + b * f), int(b * f + r * (1 - f)))
    else:
        f = (shift - 240) / 120.0
        return (int(r * f + b * (1 - f)), int(g * (1 - f)), int(b * (1 - f) + r * f))


LIGHT_PATTERNS = ['chase', 'twinkle', 'pulse', 'rainbow']


def get_random_pattern(rng=None):
    """Pick a random running light pattern."""
    r = rng or _random
    return r.choice(LIGHT_PATTERNS)


# ═══════════════════════════════════════════════════════════════════
#  Main frame renderer
# ═══════════════════════════════════════════════════════════════════
def render_frame(img_arr, t, category='home', pattern='chase',
                 frame_width=18, light_radius=5, num_lights=28):
    """Render decorative frame with running lights on an image.

    Args:
        img_arr: numpy array (H, W, 3) — the product image
        t: float — current time in seconds (for animation)
        category: str — category for color theme
        pattern: str — 'chase', 'twinkle', 'pulse', 'rainbow'
        frame_width: int — frame border thickness
        light_radius: int — radius of each light dot
        num_lights: int — number of lights around the frame

    Returns:
        numpy array (H, W, 3)
    """
    h, w = img_arr.shape[:2]
    theme = FRAME_THEMES.get(category, FRAME_THEMES['home'])

    # Work in RGBA for glow blending
    img_pil = Image.fromarray(img_arr).convert('RGBA')
    overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    margin = frame_width + 4
    fc = theme['frame_color']
    ic = theme['inner_color']

    # Outer frame border
    draw.rectangle([(0, 0), (w - 1, h - 1)], outline=(*fc, 255), width=frame_width)
    # Inner accent line
    inner_offset = frame_width - 2
    draw.rectangle([(inner_offset, inner_offset),
                     (w - 1 - inner_offset, h - 1 - inner_offset)],
                    outline=(*ic, 180), width=2)

    # Corner accents (small squares)
    cs = frame_width + 4
    for cx, cy in [(0, 0), (w - cs, 0), (0, h - cs), (w - cs, h - cs)]:
        draw.rectangle([(cx, cy), (cx + cs, cy + cs)], fill=(*fc, 220))

    # Running lights
    positions = _get_light_positions(w, h, margin - 2, num_lights)

    for i, (lx, ly) in enumerate(positions):
        if pattern == 'chase':
            brightness = _chase_brightness(i, num_lights, t)
        elif pattern == 'twinkle':
            brightness = _twinkle_brightness(i, num_lights, t)
        elif pattern == 'pulse':
            brightness = _pulse_brightness(i, num_lights, t)
        elif pattern == 'rainbow':
            brightness = _rainbow_brightness(i, num_lights, t)
        else:
            brightness = 0.5

        # Light color
        if pattern == 'rainbow':
            lc = _rainbow_color(i, num_lights, t, theme['light_color'])
        else:
            lc = theme['light_color']

        # Scale color by brightness
        r = min(255, int(lc[0] * brightness))
        g = min(255, int(lc[1] * brightness))
        b = min(255, int(lc[2] * brightness))
        alpha = int(200 * brightness + 55)

        # Bright core
        draw.ellipse([(lx - light_radius, ly - light_radius),
                       (lx + light_radius, ly + light_radius)],
                      fill=(r, g, b, alpha))

        # Subtle glow around light (larger, dimmer)
        if brightness > 0.4:
            gr = light_radius * 2
            ga = int(60 * brightness)
            draw.ellipse([(lx - gr, ly - gr), (lx + gr, ly + gr)],
                          fill=(r, g, b, ga))

    # Composite overlay onto image
    result = Image.alpha_composite(img_pil, overlay)
    return np.array(result.convert('RGB'))


def apply_vignette(img_arr, strength=0.4):
    """Apply dark vignette to edges."""
    h, w = img_arr.shape[:2]
    # Create radial gradient mask
    cy, cx = h / 2, w / 2
    Y, X = np.ogrid[:h, :w]
    # Normalized distance from center (0 at center, 1 at corners)
    dist = np.sqrt(((X - cx) / cx) ** 2 + ((Y - cy) / cy) ** 2)
    dist = np.clip(dist, 0, 1.5)

    # Vignette: darken towards edges
    mask = 1.0 - strength * (dist ** 1.5)
    mask = np.clip(mask, 0.3, 1.0)

    result = img_arr.astype(float) * mask[:, :, np.newaxis]
    return np.clip(result, 0, 255).astype(np.uint8)


def apply_ken_burns(img_arr, t, duration, direction='zoom_in'):
    """Subtle Ken Burns effect (zoom + pan) on a single image.
    Much gentler than transition — just ~3% movement."""
    h, w = img_arr.shape[:2]
    progress = min(1.0, max(0.0, t / max(duration, 0.01)))

    # Very subtle movement
    ease_p = 0.5 * (1 - math.cos(progress * math.pi))

    configs = {
        'zoom_in':   (1.00, 1.04, 0.50, 0.50, 0.49, 0.48),
        'zoom_out':  (1.04, 1.00, 0.49, 0.48, 0.50, 0.50),
        'pan_left':  (1.03, 1.03, 0.52, 0.50, 0.48, 0.50),
        'pan_right': (1.03, 1.03, 0.48, 0.50, 0.52, 0.50),
    }
    ss, es, scx, scy, ecx, ecy = configs.get(direction, configs['zoom_in'])

    scale = ss + (es - ss) * ease_p
    cx_f = scx + (ecx - scx) * ease_p
    cy_f = scy + (ecy - scy) * ease_p

    crop_w = max(1, int(w / scale))
    crop_h = max(1, int(h / scale))
    x1 = max(0, min(int(cx_f * w - crop_w / 2), w - crop_w))
    y1 = max(0, min(int(cy_f * h - crop_h / 2), h - crop_h))

    cropped = img_arr[y1:y1 + crop_h, x1:x1 + crop_w]
    return np.array(Image.fromarray(cropped).resize((w, h), Image.BILINEAR))


def fit_image_to_frame(img_pil, target_w, target_h, bg_color=(15, 15, 20)):
    """Fit product image FULL SCREEN (cover mode).
    Image fills ENTIRE screen — may crop edges if aspect ratio differs.
    Center-crops to keep the most important area (center).
    No black bars, no letterbox."""
    w, h = img_pil.size

    # COVER mode: scale to FILL (crop overflow)
    scale = max(target_w / w, target_h / h)
    new_w = int(w * scale)
    new_h = int(h * scale)

    resized = img_pil.resize((new_w, new_h), Image.LANCZOS)

    # Center-crop to exact target size
    crop_x = (new_w - target_w) // 2
    crop_y = (new_h - target_h) // 2

    cropped = resized.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))

    if cropped.mode == 'RGBA':
        # Flatten alpha onto bg color
        canvas = Image.new('RGB', (target_w, target_h), bg_color)
        canvas.paste(cropped, (0, 0), cropped.split()[3])
        return canvas

    return cropped.convert('RGB')

