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

    # (No separate glow layer — only 2 fire beams, nothing else)

    # Solid continuous line (base frame — always visible, thin)
    draw.rectangle([(fx1, fy1), (fx2, fy2)],
                    outline=(*fc, 150), width=2)

    # ── TWO FIRE BEAMS (burning fuse / sumbu petasan) ──
    # Reference: kepala besar merah, badan kuning panjang, ekor tipis menghilang
    frame_w = fx2 - fx1
    frame_h = fy2 - fy1
    perimeter = 2 * frame_w + 2 * frame_h

    speed = 0.25          # loops per second
    beam_length = perimeter * 0.45   # 45% of perimeter (panjang, sesuai referensi)
    num_segments = 150    # ultra-smooth rendering

    # Colors: RED head → YELLOW body → SILVER tail (menyatu frame)
    fire_head = (255, 30, 10)      # bright red (kepala api)
    fire_mid = (255, 200, 30)      # warm yellow (badan)
    fire_tail = fc                  # frame silver (ekor menyatu)

    # Size: head 20px → tail 2px (LINEAR gradient, smooth)
    head_width = 28       # kepala besar (body gradasi dari sini ke tail)
    tail_width = 2        # ekor = garis frame

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

    # Two beams: 180 degrees apart (half perimeter offset)
    for beam_offset in [0.0, 0.5]:
        laser_pos = ((t * speed) + beam_offset) % 1.0
        head_dist = laser_pos * perimeter

        # ── DRAW HEAD: large bright RED circle ──
        hx, hy = _dist_to_xy(head_dist)
        head_r = 12  # radius of head circle (24px diameter)
        draw.ellipse([(int(hx) - head_r, int(hy) - head_r),
                       (int(hx) + head_r, int(hy) + head_r)],
                      fill=(255, 30, 10, 255))  # bright red, full opacity
        # Glow around head
        glow_r = head_r + 6
        draw.ellipse([(int(hx) - glow_r, int(hy) - glow_r),
                       (int(hx) + glow_r, int(hy) + glow_r)],
                      fill=(255, 60, 20, 80))  # soft red glow

        # ── DRAW BODY + TAIL: gradient line segments ──
        prev_pt = None
        for seg in range(num_segments):
            seg_frac = seg / num_segments  # 0.0=head, 1.0=tail
            seg_dist = (head_dist - seg_frac * beam_length) % perimeter
            sx, sy = _dist_to_xy(seg_dist)

            # Brightness: gentle fade head->tail
            brightness = max(0.0, 1.0 - seg_frac ** 0.7)
            if brightness < 0.02:
                prev_pt = None
                continue

            # Size: LINEAR gradient head->tail (28px -> 2px)
            line_w = max(tail_width, int(head_width - (head_width - tail_width) * seg_frac))

            alpha = int(255 * min(1.0, brightness * 1.2))

            # Color: RED (0-10%) -> YELLOW (10-40%) -> SILVER (40-100%)
            if seg_frac < 0.10:
                mix = seg_frac / 0.10
                r = int(fire_head[0] * (1 - mix) + fire_mid[0] * mix)
                g = int(fire_head[1] * (1 - mix) + fire_mid[1] * mix)
                b_c = int(fire_head[2] * (1 - mix) + fire_mid[2] * mix)
            elif seg_frac < 0.40:
                mix = (seg_frac - 0.10) / 0.30
                r = int(fire_mid[0] * (1 - mix) + fire_tail[0] * mix)
                g = int(fire_mid[1] * (1 - mix) + fire_tail[1] * mix)
                b_c = int(fire_mid[2] * (1 - mix) + fire_tail[2] * mix)
            else:
                tail_fade = (seg_frac - 0.40) / 0.60
                r, g, b_c = fire_tail[0], fire_tail[1], fire_tail[2]
                alpha = int(alpha * max(0, 1.0 - tail_fade * 0.8))

            pt = (int(sx), int(sy))
            if prev_pt:
                draw.line([prev_pt, pt], fill=(r, g, b_c, alpha), width=line_w)
            prev_pt = pt

    # ════════════════════════════════════════════════════════════
    #  PIGURA DALAM — inside the outer frame, with mirror gap
    # ════════════════════════════════════════════════════════════

    if product_bounds:
        # Inner frame sits INSIDE outer frame with visible gap
        inner_margin = 50  # inner frame position from screen edge
        ix1, iy1 = inner_margin, inner_margin
        ix2, iy2 = w - 1 - inner_margin, h - 1 - inner_margin

        # ── MIRROR REFLECTION: semi-transparent overlay in gap area ──
        # Area between outer frame (12px) and inner frame (50px)
        # Dark frosted overlay — product shows through but tinted
        mirror_alpha = 35  # very transparent (product visible through)
        # Top strip
        draw.rectangle([(fx1, fy1), (fx2, iy1)],
                        fill=(10, 10, 15, mirror_alpha))
        # Bottom strip
        draw.rectangle([(fx1, iy2), (fx2, fy2)],
                        fill=(10, 10, 15, mirror_alpha))
        # Left strip
        draw.rectangle([(fx1, iy1), (ix1, iy2)],
                        fill=(10, 10, 15, mirror_alpha))
        # Right strip
        draw.rectangle([(ix2, iy1), (fx2, iy2)],
                        fill=(10, 10, 15, mirror_alpha))

        # WIDER inner frame line, MORE TRANSPARENT
        inner_fw = 5
        white_alpha = 60
        draw.rectangle([(ix1, iy1), (ix2, iy2)],
                        outline=(255, 255, 255, white_alpha), width=inner_fw)

        # Corner accents: proportional to line width (flexible)
        corner_len = inner_fw * 18   # 90px
        corner_thick = inner_fw + 3  # 8px
        corner_alpha = 140
        corner_color = (255, 255, 255, corner_alpha)

        # Top-left corner
        draw.line([(ix1, iy1), (ix1 + corner_len, iy1)], fill=corner_color, width=corner_thick)
        draw.line([(ix1, iy1), (ix1, iy1 + corner_len)], fill=corner_color, width=corner_thick)
        # Top-right corner
        draw.line([(ix2, iy1), (ix2 - corner_len, iy1)], fill=corner_color, width=corner_thick)
        draw.line([(ix2, iy1), (ix2, iy1 + corner_len)], fill=corner_color, width=corner_thick)
        # Bottom-left corner
        draw.line([(ix1, iy2), (ix1 + corner_len, iy2)], fill=corner_color, width=corner_thick)
        draw.line([(ix1, iy2), (ix1, iy2 - corner_len)], fill=corner_color, width=corner_thick)
        # Bottom-right corner
        draw.line([(ix2, iy2), (ix2 - corner_len, iy2)], fill=corner_color, width=corner_thick)
        draw.line([(ix2, iy2), (ix2, iy2 - corner_len)], fill=corner_color, width=corner_thick)

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
    """Place product image — STRETCH to fill ENTIRE frame. ZERO gaps.

    Quality enhancement pipeline (tuned for 800px+ source images):
      1. Auto-trim white padding from Shopee images
      2. Detect image quality (blur, noise, low contrast)
      3. Denoise ONLY truly degraded source images
      4. Multi-step upscale (prevents blur on large scale ratios)
      5. Light adaptive sharpening (preserve natural look)
      6. Gentle color normalization (no over-processing)
      → ZERO space, ZERO gaps, ZERO cropping
    """
    from PIL import ImageEnhance, ImageStat

    img_rgb = img_pil.convert('RGB')

    # ── Step 1: Auto-trim ONLY pure white padding ──
    img_trimmed = _safe_trim_white(img_rgb)
    src_w, src_h = img_trimmed.size

    # ── Step 2: Detect source image quality ──
    arr = np.array(img_trimmed)
    # Blur detection: low variance = blurry image
    gray = np.mean(arr, axis=2)
    laplacian_var = np.var(gray[1:, :] - gray[:-1, :])  # edge variance
    is_blurry = laplacian_var < 150  # only truly blurry images
    # Contrast detection: narrow histogram = low contrast
    img_std = np.std(arr)
    is_low_contrast = img_std < 30  # only truly flat images
    # Resolution detection — with min 800px gate, this rarely triggers
    is_small = src_w < 400 or src_h < 400
    needs_heavy_enhance = is_blurry and is_small  # BOTH must be true

    # ── Step 3: Denoise ONLY truly degraded source images ──
    work = img_trimmed
    if needs_heavy_enhance:
        # Only denoise if image is both small AND blurry
        work = work.filter(ImageFilter.MedianFilter(size=3))

    # ── Step 4: Multi-step upscale for quality ──
    scale_x = target_w / src_w
    scale_y = target_h / src_h
    max_scale = max(scale_x, scale_y)

    if max_scale > 2.5:
        # Very large upscale: intermediate step to reduce artifacts
        mid_w = min(target_w, src_w * 2)
        mid_h = min(target_h, src_h * 2)
        product = work.resize((mid_w, mid_h), Image.LANCZOS)
        # Light sharpen at intermediate step
        product = product.filter(ImageFilter.UnsharpMask(radius=1.0, percent=40, threshold=3))
        # Final size
        product = product.resize((target_w, target_h), Image.LANCZOS)
    else:
        product = work.resize((target_w, target_h), Image.LANCZOS)

    # ── Step 5: Light adaptive sharpening (preserve natural look) ──
    if needs_heavy_enhance:
        # Truly degraded source: moderate sharpening
        product = product.filter(ImageFilter.UnsharpMask(radius=1.5, percent=80, threshold=3))
    elif max_scale > 1.5:
        # Noticeable upscale: light sharpening to restore detail
        product = product.filter(ImageFilter.UnsharpMask(radius=1.0, percent=50, threshold=3))
    # else: good quality source with small upscale — LANCZOS is enough, no extra sharpen

    # ── Step 6: Gentle color normalization ──
    from PIL import ImageOps
    # Very gentle autocontrast (just clip extremes, don't remap entire range)
    product = ImageOps.autocontrast(product, cutoff=0.3)

    # Subtle contrast boost (makes image "pop" without washing out)
    product = ImageEnhance.Contrast(product).enhance(1.05)

    # Subtle color saturation boost (more vivid, not oversaturated)
    product = ImageEnhance.Color(product).enhance(1.05)

    # NO extra Sharpness boost — already handled in step 5
    # Double-sharpening was causing halo artifacts + unnatural look

    # Canvas = product itself (fills everything)
    canvas = product.copy()

    # Product bounds = the FULL canvas (frame draws ON TOP as overlay)
    product_bounds = (0, 0, target_w, target_h)
    return canvas, product_bounds


def _safe_trim_white(img_rgb):
    """Trim ONLY pure white/near-white padding from Shopee images.

    Very conservative:
    - Threshold 252 (only near-pure-white counts as 'border')
    - Max 20% trim from any edge (safety guard)
    - If image has no white padding, returns unchanged
    """
    arr = np.array(img_rgb)
    oh, ow = arr.shape[:2]

    # Only pixels where ALL channels >= 252 are considered 'white padding'
    if len(arr.shape) == 3:
        is_white = np.all(arr >= 252, axis=2)
    else:
        is_white = arr >= 252

    has_content = ~is_white  # non-white = content

    if not has_content.any():
        return img_rgb  # All white — return as-is

    rows = np.any(has_content, axis=1)
    cols = np.any(has_content, axis=0)

    if not rows.any() or not cols.any():
        return img_rgb

    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]

    # Safety: don't trim more than 20% from any edge
    max_trim_y = int(oh * 0.20)
    max_trim_x = int(ow * 0.20)
    rmin = min(rmin, max_trim_y)
    rmax = max(rmax, oh - 1 - max_trim_y)
    cmin = min(cmin, max_trim_x)
    cmax = max(cmax, ow - 1 - max_trim_x)

    trimmed = img_rgb.crop((cmin, rmin, cmax + 1, rmax + 1))

    tw, th = trimmed.size
    if tw < ow * 0.5 or th < oh * 0.5:
        return img_rgb  # Too aggressive — skip

    return trimmed


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

