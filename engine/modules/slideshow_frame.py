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
#  Frame color themes — SILVER/PEWTER matching frosted mirror
#  Both frames use silver tones that blend with the dark mirror bg
#  Slightly brighter than the frosted glass for subtle visibility
# ═══════════════════════════════════════════════════════════════════
_SILVER_THEME = {
    'frame_color': (180, 185, 190),         # Silver (pigura luar)
    'light_color': (210, 215, 220),         # Light silver (lampu)
    'glow_color': (170, 175, 180, 50),      # Soft silver glow
    'inner_color': (155, 160, 165),         # Darker pewter (pigura dalam)
}

FRAME_THEMES = {
    'fashion':  _SILVER_THEME,
    'gadget':   _SILVER_THEME,
    'beauty':   _SILVER_THEME,
    'home':     _SILVER_THEME,
    'wellness': _SILVER_THEME,
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


def _chase_brightness(light_index, num_lights, t, speed=1.5):
    """Chase pattern: bright dot moves clockwise around the frame.
    speed=1.5 means 1.5 full loops per second (visible, not too fast).
    Wider Gaussian tail (0.04) so ~4-5 lights glow at once."""
    phase = (t * speed - light_index / num_lights) % 1.0
    # Wide Gaussian so multiple lights glow (visible chase tail)
    b = math.exp(-((phase - 0.5) ** 2) / 0.04)
    # Base brightness so lights aren't fully dark
    return max(0.08, min(1.0, b * 0.92 + 0.08))


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
                 frame_width=4, light_radius=4, num_lights=36,
                 product_bounds=None):
    """Render TWO-LAYER frame matching reference video:

    PIGURA LUAR (outer): Thin neon frame at screen edge + running chase lights
    PIGURA DALAM (inner): Wraps directly ON the product image edges
                          Bold corners, acts as border between product & mirror

    Args:
        product_bounds: tuple (x1, y1, x2, y2) of product position on screen
    """
    h, w = img_arr.shape[:2]
    theme = FRAME_THEMES.get(category, FRAME_THEMES['home'])

    img_pil = Image.fromarray(img_arr).convert('RGBA')
    overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    fc = theme['frame_color']
    ic = theme['inner_color']
    gc = theme['glow_color']
    lc = theme['light_color']

    # ════════════════════════════════════════════════════════════
    #  PIGURA LUAR — solid line frame with laser beam chase
    #  Position: 12px inward from screen edge (visible gap)
    # ════════════════════════════════════════════════════════════

    outer_margin = 12  # visible gap between screen edge and frame
    fx1, fy1 = outer_margin, outer_margin
    fx2, fy2 = w - 1 - outer_margin, h - 1 - outer_margin

    # Soft glow behind frame
    glow_layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    glow_draw.rectangle([(fx1 - 4, fy1 - 4), (fx2 + 4, fy2 + 4)],
                         outline=gc, width=10)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=5))
    overlay = Image.alpha_composite(overlay, glow_layer)
    draw = ImageDraw.Draw(overlay)

    # Solid continuous line (base frame — always visible, thin)
    draw.rectangle([(fx1, fy1), (fx2, fy2)],
                    outline=(*fc, 150), width=2)

    # ── TWO FIRE BEAMS chasing each other (burning fuse / sumbu petasan) ──
    frame_w = fx2 - fx1
    frame_h = fy2 - fy1
    perimeter = 2 * frame_w + 2 * frame_h

    speed = 0.18  # loops per second (slow, like burning fuse)
    beam_length = perimeter * 0.33  # 1/3 of perimeter lit (panjang)
    num_segments = 120  # smooth resolution

    # Fire colors: head = RED (api), mid = YELLOW, tail = frame silver
    fire_head = (255, 30, 10)      # bright red (kepala api)
    fire_mid = (255, 200, 30)      # yellow (tengah)
    fire_tail = fc                  # fades to frame silver (ekor menyatu)

    # Outer frame line width (for reference — tail matches this)
    frame_line_w = 2

    def _dist_to_xy(d):
        """Convert distance along perimeter to (x, y) coordinates."""
        d = d % perimeter
        if d < frame_w:
            return fx1 + d, fy1
        elif d < frame_w + frame_h:
            return fx2, fy1 + (d - frame_w)
        elif d < 2 * frame_w + frame_h:
            return fx2 - (d - frame_w - frame_h), fy2
        else:
            return fx1, fy2 - (d - 2 * frame_w - frame_h)

    # Two beams: 180° apart (half perimeter offset)
    for beam_offset in [0.0, 0.5]:
        laser_pos = ((t * speed) + beam_offset) % 1.0
        head_dist = laser_pos * perimeter

        # Draw burning fuse: connected line segments from head to tail
        prev_pt = None
        for seg in range(num_segments):
            seg_frac = seg / num_segments  # 0=head, 1=tail
            seg_dist = (head_dist - seg_frac * beam_length) % perimeter
            sx, sy = _dist_to_xy(seg_dist)

            # Brightness fades: head=1.0, tail→0.0 (gradual)
            brightness = 1.0 - (seg_frac ** 0.6)
            if brightness < 0.02:
                prev_pt = None
                continue

            # Line width: head=14px (BIGGER than frame), tail=2px (= frame line)
            # Kepala membakar garis frame, ekor kembali ke ukuran garis
            line_w = max(frame_line_w, int(frame_line_w + 12 * brightness))
            alpha = int(255 * brightness)

            # Color gradient: RED (head) → YELLOW (mid) → SILVER (tail)
            if seg_frac < 0.15:
                # Head zone: bright RED (api menyala)
                mix = seg_frac / 0.15
                r = int(fire_head[0] * (1 - mix) + fire_mid[0] * mix)
                g = int(fire_head[1] * (1 - mix) + fire_mid[1] * mix)
                b_c = int(fire_head[2] * (1 - mix) + fire_mid[2] * mix)
            elif seg_frac < 0.45:
                # Mid zone: YELLOW → fading
                mix = (seg_frac - 0.15) / 0.30
                r = int(fire_mid[0] * (1 - mix) + fire_tail[0] * mix)
                g = int(fire_mid[1] * (1 - mix) + fire_tail[1] * mix)
                b_c = int(fire_mid[2] * (1 - mix) + fire_tail[2] * mix)
            else:
                # Tail zone: frame silver (api habis, menyatu dengan pigura)
                r, g, b_c = fire_tail[0], fire_tail[1], fire_tail[2]

            pt = (int(sx), int(sy))
            if prev_pt:
                draw.line([prev_pt, pt], fill=(r, g, b_c, alpha), width=line_w)
            prev_pt = pt

    # ════════════════════════════════════════════════════════════
    #  PIGURA DALAM — wraps ON product image edges
    # ════════════════════════════════════════════════════════════

    if product_bounds:
        px1, py1, px2, py2 = product_bounds
        inner_fw = 8  # THICK frame wrapping product
        draw.rectangle([(px1, py1), (px2, py2)],
                        outline=(*ic, 240), width=inner_fw)

        # Bold corner accents (L-shapes at 4 corners)
        corner_size = 30
        corner_thick = 7
        draw.line([(px1, py1), (px1 + corner_size, py1)], fill=(*fc, 255), width=corner_thick)
        draw.line([(px1, py1), (px1, py1 + corner_size)], fill=(*fc, 255), width=corner_thick)
        draw.line([(px2, py1), (px2 - corner_size, py1)], fill=(*fc, 255), width=corner_thick)
        draw.line([(px2, py1), (px2, py1 + corner_size)], fill=(*fc, 255), width=corner_thick)
        draw.line([(px1, py2), (px1 + corner_size, py2)], fill=(*fc, 255), width=corner_thick)
        draw.line([(px1, py2), (px1, py2 - corner_size)], fill=(*fc, 255), width=corner_thick)
        draw.line([(px2, py2), (px2 - corner_size, py2)], fill=(*fc, 255), width=corner_thick)
        draw.line([(px2, py2), (px2, py2 - corner_size)], fill=(*fc, 255), width=corner_thick)

    # Composite
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


def _auto_trim_whitespace(img_rgb):
    """Remove white/light borders from product images.

    Many Shopee seller images have white/light padding around the product.
    This trims those borders so the product fills the frame completely.
    """
    arr = np.array(img_rgb)
    oh, ow = arr.shape[:2]

    # Find non-white/non-light pixels (threshold: any channel < 245)
    # More aggressive than before to catch light gray borders too
    if len(arr.shape) == 3:
        mask = np.any(arr < 245, axis=2)
    else:
        mask = arr < 245

    if not mask.any():
        return img_rgb  # All white/light — return as-is

    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)

    if not rows.any() or not cols.any():
        return img_rgb

    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]

    # NO re-padding — trim tight to content (padding caused border gaps)
    trimmed = img_rgb.crop((cmin, rmin, cmax + 1, rmax + 1))

    # Only use trimmed if it didn't remove too much (>50% = too aggressive)
    tw, th = trimmed.size
    if tw < ow * 0.5 or th < oh * 0.5:
        return img_rgb
    return trimmed


def fit_image_to_frame(img_pil, target_w, target_h, bg_color=(15, 15, 20)):
    """Place product image using FIT mode — 100% content preserved, ZERO cropping.

    Strategy:
      1. Full screen = frosted mirror background (blurred product reflection)
      2. Product rectangle = proportional margins
      3. FIT mode = scale to fit WITHIN rectangle, maintain aspect ratio
         → Image is NEVER cropped — all text, branding, product details visible
         → Any gap between product and frame is filled by frosted mirror
         → Frosted mirror creates elegant seamless extension
    """
    from PIL import ImageEnhance
    w, h = img_pil.size
    img_rgb = img_pil.convert('RGB')

    # ── Step 1: Full-screen frosted mirror background ──
    bg_scale = max(target_w / w, target_h / h) * 1.3
    bg_w = int(w * bg_scale)
    bg_h = int(h * bg_scale)
    bg_img = img_rgb.resize((bg_w, bg_h), Image.LANCZOS)
    crop_x = (bg_w - target_w) // 2
    crop_y = (bg_h - target_h) // 2
    bg_cropped = bg_img.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))
    frosted = bg_cropped.filter(ImageFilter.GaussianBlur(radius=18))
    frosted = ImageEnhance.Brightness(frosted).enhance(0.80)
    frosted = ImageEnhance.Color(frosted).enhance(0.75)

    # ── Step 2: Define product rectangle (matching reference layout) ──
    margin_x_pct = 0.10   # 10% each side left/right (~108px on 1080)
    margin_y_pct = 0.12   # 12% each side top/bottom (~230px on 1920)
    rect_x = int(target_w * margin_x_pct)
    rect_y = int(target_h * margin_y_pct)
    rect_w = target_w - 2 * rect_x
    rect_h = target_h - 2 * rect_y

    # ── Step 3: FIT mode — scale to fit, center, NO cropping ──
    # Maintain original aspect ratio — product is NEVER distorted or cropped
    fit_scale = min(rect_w / w, rect_h / h)
    scaled_w = int(w * fit_scale)
    scaled_h = int(h * fit_scale)
    product = img_rgb.resize((scaled_w, scaled_h), Image.LANCZOS)

    # Sharpen after resize
    product = product.filter(ImageFilter.UnsharpMask(radius=1.5, percent=80, threshold=2))

    # ── Step 4: Center product on frosted mirror background ──
    # Gap areas are filled by frosted mirror (elegant seamless extension)
    canvas = frosted.copy()
    paste_x = rect_x + (rect_w - scaled_w) // 2
    paste_y = rect_y + (rect_h - scaled_h) // 2
    canvas.paste(product, (paste_x, paste_y))

    # Product bounds = actual product edges (for inner frame drawing)
    product_bounds = (paste_x, paste_y, paste_x + scaled_w, paste_y + scaled_h)
    return canvas, product_bounds


def _get_light_positions_rect(x1, y1, x2, y2, num_lights=28):
    """Calculate light positions evenly distributed around a rectangle."""
    positions = []
    w = x2 - x1
    h = y2 - y1
    perimeter = 2 * w + 2 * h
    seg = perimeter / num_lights

    for i in range(num_lights):
        d = i * seg
        if d < w:  # Top edge
            positions.append((int(x1 + d), y1))
        elif d < w + h:  # Right edge
            dd = d - w
            positions.append((x2, int(y1 + dd)))
        elif d < 2 * w + h:  # Bottom edge
            dd = d - w - h
            positions.append((int(x2 - dd), y2))
        else:  # Left edge
            dd = d - 2 * w - h
            positions.append((x1, int(y2 - dd)))

    return positions

