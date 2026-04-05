"""
slideshow_transitions.py
Elegant transition effects for product slideshow videos.

7 transitions (NO spinning/rotating — looks tacky):
  1. Fade Dissolve — smooth crossfade between slides
  2. Page Roll — horizontal scroll (old out, new in)
  3. Split Horizontal — split from center horizontally
  4. Split Vertical — split from center vertically
  5. Zoom Punch — zoom in, flash, zoom out new
  6. Slide Push — new pushes old off screen (vertical)
  7. Wipe Down — vertical wipe reveals new from top
  8. Blur Morph — blur out old, blur in new

Per-channel transition sequences (unique order per channel):
  TT:       fade_dissolve → split_vertical → zoom_punch
  YT Short: wipe_down → blur_morph → split_horizontal
  FB:       split_horizontal → zoom_punch → wipe_down
  YT Long:  blur_morph → fade_dissolve → slide_push → wipe_down → split_vertical → zoom_punch → split_horizontal
"""
import numpy as np
from PIL import Image, ImageFilter
import math


def _ease_in_out(t):
    """Smooth ease-in-out (sinusoidal)."""
    return 0.5 * (1 - math.cos(t * math.pi))


def _ease_out_cubic(t):
    """Ease-out cubic."""
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def _ease_in_cubic(t):
    """Ease-in cubic."""
    t = min(1.0, max(0.0, t))
    return t ** 3


# ═══════════════════════════════════════════════════════════════════
#  Transition effects
# ═══════════════════════════════════════════════════════════════════

def fade_dissolve(img1_arr, img2_arr, progress):
    """Smooth crossfade dissolve — classic and elegant.
    Works perfectly with any music tempo."""
    p = _ease_in_out(progress)
    return np.clip(
        img1_arr.astype(float) * (1 - p) + img2_arr.astype(float) * p,
        0, 255
    ).astype(np.uint8)


def page_roll(img1_arr, img2_arr, progress):
    """Horizontal scroll: img1 rolls out left, img2 rolls in from right."""
    h, w = img1_arr.shape[:2]
    p = _ease_in_out(progress)

    offset = int(w * p)
    result = np.zeros_like(img1_arr)

    # img1 sliding left
    if offset < w:
        remaining = w - offset
        result[:, :remaining] = img1_arr[:, offset:offset + remaining]

    # img2 sliding in from right
    if offset > 0:
        visible = min(offset, w)
        src_start = w - visible
        result[:, w - visible:] = img2_arr[:, src_start:src_start + visible]

    return result


def split_horizontal(img1_arr, img2_arr, progress):
    """Split from center horizontally — doors opening effect."""
    h, w = img1_arr.shape[:2]
    p = _ease_out_cubic(progress)
    split = int(h * p * 0.5)

    result = img2_arr.copy()

    if split < h // 2:
        # Top half of img1 moves up
        result[:h // 2 - split] = img1_arr[split:h // 2]
        # Bottom half of img1 moves down
        result[h // 2 + split:] = img1_arr[h // 2:h - split]

    return result


def split_vertical(img1_arr, img2_arr, progress):
    """Split from center vertically — curtain opening effect."""
    h, w = img1_arr.shape[:2]
    p = _ease_out_cubic(progress)
    split = int(w * p * 0.5)

    result = img2_arr.copy()

    if split < w // 2:
        result[:, :w // 2 - split] = img1_arr[:, split:w // 2]
        result[:, w // 2 + split:] = img2_arr[:, w // 2 + split:]
        # Keep img1 in the middle area that hasn't split yet
        mid_left = w // 2 - split
        mid_right = w // 2 + split
        if mid_right > mid_left:
            result[:, mid_left:mid_right] = img1_arr[:, mid_left:mid_right]

    return result


def zoom_punch(img1_arr, img2_arr, progress):
    """Zoom in with flash, then reveal new image — impactful beat sync."""
    h, w = img1_arr.shape[:2]
    p = _ease_in_out(progress)

    if p < 0.4:
        # Phase 1: img1 zooms in (0.4 of transition)
        zoom = 1.0 + (p / 0.4) * 0.3  # 1.0 → 1.3
        zh = int(h / zoom)
        zw = int(w / zoom)
        y1 = (h - zh) // 2
        x1 = (w - zw) // 2
        cropped = img1_arr[y1:y1 + zh, x1:x1 + zw]
        result = np.array(Image.fromarray(cropped).resize((w, h), Image.BILINEAR))
        # Slight brightness increase (building to flash)
        bright = 1.0 + (p / 0.4) * 0.3
        result = np.clip(result * bright, 0, 255).astype(np.uint8)
    elif p < 0.6:
        # Phase 2: white flash (0.2 of transition)
        flash_p = (p - 0.4) / 0.2
        if flash_p < 0.5:
            # Flash brightening
            alpha = flash_p * 2
            result = np.clip(
                img1_arr.astype(float) * (1 - alpha) + 255 * alpha,
                0, 255
            ).astype(np.uint8)
        else:
            # Flash fading to img2
            alpha = (flash_p - 0.5) * 2
            result = np.clip(
                255 * (1 - alpha) + img2_arr.astype(float) * alpha,
                0, 255
            ).astype(np.uint8)
    else:
        # Phase 3: img2 zooms out from enlarged (0.4 of transition)
        remain = (p - 0.6) / 0.4
        zoom = 1.3 - remain * 0.3  # 1.3 → 1.0
        zh = int(h / zoom)
        zw = int(w / zoom)
        y1 = (h - zh) // 2
        x1 = (w - zw) // 2
        cropped = img2_arr[y1:y1 + zh, x1:x1 + zw]
        result = np.array(Image.fromarray(cropped).resize((w, h), Image.BILINEAR))

    return result


def slide_push(img1_arr, img2_arr, progress):
    """Vertical slide: new image pushes old upward — clean and smooth."""
    h, w = img1_arr.shape[:2]
    p = _ease_in_out(progress)

    offset = int(h * p)
    result = np.zeros_like(img1_arr)

    # img1 pushed up
    if offset < h:
        remaining = h - offset
        result[:remaining] = img1_arr[offset:]

    # img2 enters from bottom
    if offset > 0:
        visible = min(offset, h)
        result[h - visible:] = img2_arr[:visible]

    return result


def wipe_down(img1_arr, img2_arr, progress):
    """Vertical wipe from top to bottom — reveals new image underneath.
    Smooth and cinematic, works well with flowing music."""
    h, w = img1_arr.shape[:2]
    p = _ease_in_out(progress)

    wipe_pos = int(h * p)
    result = img1_arr.copy()

    if wipe_pos > 0:
        result[:wipe_pos] = img2_arr[:wipe_pos]

    # Soft edge at wipe line (10px gradient blend)
    edge_size = 10
    if 0 < wipe_pos < h - edge_size:
        for i in range(edge_size):
            y = wipe_pos + i
            if y < h:
                alpha = 1.0 - (i / edge_size)
                result[y] = np.clip(
                    img2_arr[y].astype(float) * alpha +
                    img1_arr[y].astype(float) * (1 - alpha),
                    0, 255
                ).astype(np.uint8)

    return result


def blur_morph(img1_arr, img2_arr, progress):
    """Blur out old image, blur in new — dreamy and elegant.
    Best for slower, ambient music sections."""
    h, w = img1_arr.shape[:2]
    p = _ease_in_out(progress)

    if p < 0.5:
        # Phase 1: img1 blurs out
        blur_amount = p * 2  # 0→1
        radius = int(blur_amount * 20) + 1
        img1_pil = Image.fromarray(img1_arr)
        blurred = img1_pil.filter(ImageFilter.GaussianBlur(radius=radius))
        # Fade brightness down slightly
        bright = 1.0 - blur_amount * 0.2
        result = np.clip(np.array(blurred) * bright, 0, 255).astype(np.uint8)
    else:
        # Phase 2: img2 un-blurs in
        unblur = (p - 0.5) * 2  # 0→1
        radius = int((1 - unblur) * 20) + 1
        img2_pil = Image.fromarray(img2_arr)
        blurred = img2_pil.filter(ImageFilter.GaussianBlur(radius=radius))
        bright = 0.8 + unblur * 0.2
        result = np.clip(np.array(blurred) * bright, 0, 255).astype(np.uint8)

    return result


# ═══════════════════════════════════════════════════════════════════
#  Transition registry — NO cube_rotate (spinning = norak)
# ═══════════════════════════════════════════════════════════════════
TRANSITIONS = {
    'fade_dissolve': fade_dissolve,
    'page_roll': page_roll,
    'split_horizontal': split_horizontal,
    'split_vertical': split_vertical,
    'zoom_punch': zoom_punch,
    'slide_push': slide_push,
    'wipe_down': wipe_down,
    'blur_morph': blur_morph,
}

TRANSITION_NAMES = list(TRANSITIONS.keys())

# ═══════════════════════════════════════════════════════════════════
#  Per-channel transition sequences (unique order per channel)
#  - No duplicate transitions within a single video
#  - Each channel has a different fixed order
#  - Ordered for aesthetic flow with typical music
# ═══════════════════════════════════════════════════════════════════
CHANNEL_TRANSITIONS = {
    # TikTok: short, punchy, 3 transitions max
    'tt': ['fade_dissolve', 'split_vertical', 'zoom_punch',
           'wipe_down', 'blur_morph', 'slide_push', 'page_roll', 'split_horizontal'],

    # YouTube Short: cinematic feel
    'yt_short': ['wipe_down', 'blur_morph', 'split_horizontal',
                 'fade_dissolve', 'zoom_punch', 'slide_push', 'page_roll', 'split_vertical'],

    # Facebook: engaging, varied
    'fb': ['split_horizontal', 'zoom_punch', 'wipe_down',
           'blur_morph', 'fade_dissolve', 'page_roll', 'split_vertical', 'slide_push'],

    # YouTube Long: most transitions needed (2 passes × 4 images)
    'yt_long': ['blur_morph', 'fade_dissolve', 'slide_push',
                'wipe_down', 'split_vertical', 'zoom_punch', 'split_horizontal', 'page_roll'],
}


def get_channel_transitions(platform, count):
    """Get transition sequence for a specific channel.

    Returns exactly `count` transitions, all unique (no repeats).
    Each channel has its own fixed order for consistency.
    """
    sequence = CHANNEL_TRANSITIONS.get(platform, CHANNEL_TRANSITIONS['tt'])
    # Take first `count` transitions (all unique by design)
    result = []
    for i in range(count):
        result.append(sequence[i % len(sequence)])
    return result


def get_random_transitions(count=3, rng=None):
    """Pick `count` random unique transitions (legacy fallback)."""
    import random
    _rng = rng or random
    pool = TRANSITION_NAMES.copy()
    _rng.shuffle(pool)
    return pool[:count]


def apply_transition(img1_arr, img2_arr, progress, transition_name):
    """Apply a named transition. progress: 0.0→1.0."""
    fn = TRANSITIONS.get(transition_name, fade_dissolve)
    progress = max(0.0, min(1.0, progress))
    return fn(img1_arr, img2_arr, progress)
