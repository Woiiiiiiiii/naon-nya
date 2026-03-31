"""
slideshow_transitions.py
Creative transition effects for product slideshow videos.

6 transitions:
  1. Cube Rotate — 3D perspective rotate to next face
  2. Page Roll — horizontal scroll (old out, new in)
  3. Split Horizontal — split from center, reveal behind
  4. Split Vertical — split from center vertically
  5. Zoom Punch — zoom in, flash, zoom out new
  6. Slide Push — new pushes old off screen
"""
import numpy as np
from PIL import Image
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


def cube_rotate(img1_arr, img2_arr, progress):
    """3D cube rotation transition.
    img1 rotates away, img2 appears from the side.
    progress: 0.0 → 1.0
    """
    h, w = img1_arr.shape[:2]
    p = _ease_in_out(progress)

    result = np.zeros_like(img1_arr)

    if p < 0.5:
        # First half: img1 shrinks from right side (perspective)
        squeeze = p * 2  # 0→1
        # Left edge stays, right edge moves inward
        right_x = int(w * (1 - squeeze * 0.6))
        if right_x < 10:
            right_x = 10
        # Top/bottom squeeze on right side for perspective
        top_squeeze = int(h * squeeze * 0.15)
        bot_squeeze = h - top_squeeze

        img1_pil = Image.fromarray(img1_arr)
        # Create perspective transform
        src = [(0, 0), (w, 0), (w, h), (0, h)]
        dst = [(0, 0), (right_x, top_squeeze), (right_x, bot_squeeze), (0, h)]
        try:
            coeffs = _find_perspective_coeffs(src, dst)
            transformed = img1_pil.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BILINEAR)
            result = np.array(transformed)
        except Exception:
            # Fallback: simple horizontal squeeze
            crop_w = max(1, int(w * (1 - squeeze * 0.5)))
            resized = Image.fromarray(img1_arr).resize((crop_w, h), Image.BILINEAR)
            result[:, :crop_w] = np.array(resized)

        # Darken based on progress (shadow on rotating face)
        shadow = max(0.5, 1.0 - squeeze * 0.4)
        result = np.clip(result * shadow, 0, 255).astype(np.uint8)
    else:
        # Second half: img2 appears from right side
        expand = (p - 0.5) * 2  # 0→1
        left_x = int(w * (1 - expand) * 0.6)
        top_squeeze = int(h * (1 - expand) * 0.15)
        bot_squeeze = h - top_squeeze

        img2_pil = Image.fromarray(img2_arr)
        src = [(0, 0), (w, 0), (w, h), (0, h)]
        dst = [(left_x, top_squeeze), (w, 0), (w, h), (left_x, bot_squeeze)]
        try:
            coeffs = _find_perspective_coeffs(src, dst)
            transformed = img2_pil.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BILINEAR)
            result = np.array(transformed)
        except Exception:
            start_x = max(0, int(w * (1 - expand)))
            visible_w = w - start_x
            if visible_w > 0:
                resized = Image.fromarray(img2_arr).resize((visible_w, h), Image.BILINEAR)
                result[:, start_x:start_x + visible_w] = np.array(resized)

        shadow = max(0.5, expand * 0.5 + 0.5)
        result = np.clip(result * shadow, 0, 255).astype(np.uint8)

    return result


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
    """Top and bottom halves of img1 split apart, revealing img2 behind."""
    h, w = img1_arr.shape[:2]
    p = _ease_out_cubic(progress)

    # Start with img2 as background
    result = img2_arr.copy()

    gap = int(h * 0.5 * p)  # How far each half has moved

    mid = h // 2

    if gap < mid:
        # Top half moves up
        top_src_start = gap
        top_remaining = mid - gap
        if top_remaining > 0:
            result[:top_remaining] = img1_arr[top_src_start:top_src_start + top_remaining]

        # Bottom half moves down
        bot_dst_start = mid + gap
        bot_remaining = h - bot_dst_start
        if bot_remaining > 0 and mid + bot_remaining <= h:
            result[bot_dst_start:bot_dst_start + bot_remaining] = img1_arr[mid:mid + bot_remaining]

    return result


def split_vertical(img1_arr, img2_arr, progress):
    """Left and right halves of img1 split apart, revealing img2 behind."""
    h, w = img1_arr.shape[:2]
    p = _ease_out_cubic(progress)

    result = img2_arr.copy()

    gap = int(w * 0.5 * p)
    mid = w // 2

    if gap < mid:
        # Left half moves left
        left_remaining = mid - gap
        if left_remaining > 0:
            result[:, :left_remaining] = img1_arr[:, gap:gap + left_remaining]

        # Right half moves right
        right_start = mid + gap
        right_remaining = w - right_start
        if right_remaining > 0 and mid + right_remaining <= w:
            result[:, right_start:right_start + right_remaining] = img1_arr[:, mid:mid + right_remaining]

    return result


def zoom_punch(img1_arr, img2_arr, progress):
    """Zoom into img1, flash white, zoom out from img2."""
    h, w = img1_arr.shape[:2]
    p = progress

    if p < 0.4:
        # Zoom into img1
        zoom_p = p / 0.4  # 0→1
        scale = 1.0 + zoom_p * 0.4  # 1.0→1.4
        cw = max(1, int(w / scale))
        ch = max(1, int(h / scale))
        x1 = (w - cw) // 2
        y1 = (h - ch) // 2
        x1 = max(0, min(x1, w - cw))
        y1 = max(0, min(y1, h - ch))
        cropped = img1_arr[y1:y1 + ch, x1:x1 + cw]
        result = np.array(Image.fromarray(cropped).resize((w, h), Image.BILINEAR))
        # Fade to white
        white_blend = zoom_p * zoom_p  # Accelerating
        result = np.clip(result * (1 - white_blend) + 255 * white_blend, 0, 255).astype(np.uint8)
        return result

    elif p < 0.6:
        # White flash
        return np.full_like(img1_arr, 255)

    else:
        # Zoom out from img2
        zoom_p = (p - 0.6) / 0.4  # 0→1
        ep = _ease_out_cubic(zoom_p)
        scale = 1.4 - ep * 0.4  # 1.4→1.0
        cw = max(1, int(w / scale))
        ch = max(1, int(h / scale))
        x1 = (w - cw) // 2
        y1 = (h - ch) // 2
        x1 = max(0, min(x1, w - cw))
        y1 = max(0, min(y1, h - ch))
        cropped = img2_arr[y1:y1 + ch, x1:x1 + cw]
        result = np.array(Image.fromarray(cropped).resize((w, h), Image.BILINEAR))
        # Fade from white
        white_blend = (1 - zoom_p) ** 2
        result = np.clip(result * (1 - white_blend) + 255 * white_blend, 0, 255).astype(np.uint8)
        return result


def slide_push(img1_arr, img2_arr, progress):
    """img2 pushes img1 off to the left (carousel style)."""
    h, w = img1_arr.shape[:2]
    p = _ease_in_out(progress)

    offset = int(w * p)
    result = np.zeros_like(img1_arr)

    # img1 being pushed left
    if offset < w:
        visible = w - offset
        result[:, :visible] = img1_arr[:, offset:]

    # img2 coming in from right
    if offset > 0:
        visible = min(offset, w)
        result[:, w - visible:] = img2_arr[:, :visible]

    return result


# ═══════════════════════════════════════════════════════════════════
#  Transition registry
# ═══════════════════════════════════════════════════════════════════
TRANSITIONS = {
    'cube_rotate': cube_rotate,
    'page_roll': page_roll,
    'split_horizontal': split_horizontal,
    'split_vertical': split_vertical,
    'zoom_punch': zoom_punch,
    'slide_push': slide_push,
}

TRANSITION_NAMES = list(TRANSITIONS.keys())


def get_random_transitions(count=3, rng=None):
    """Pick `count` random unique transitions."""
    import random
    _rng = rng or random
    pool = TRANSITION_NAMES.copy()
    _rng.shuffle(pool)
    return pool[:count]


def apply_transition(img1_arr, img2_arr, progress, transition_name):
    """Apply a named transition. progress: 0.0→1.0."""
    fn = TRANSITIONS.get(transition_name, slide_push)
    progress = max(0.0, min(1.0, progress))
    return fn(img1_arr, img2_arr, progress)


# ═══════════════════════════════════════════════════════════════════
#  Perspective transform helper
# ═══════════════════════════════════════════════════════════════════
def _find_perspective_coeffs(src, dst):
    """Find coefficients for PIL Image.PERSPECTIVE transform.
    src and dst are lists of 4 (x,y) corner points."""
    import numpy as np
    matrix = []
    for s, d in zip(src, dst):
        matrix.append([d[0], d[1], 1, 0, 0, 0, -s[0]*d[0], -s[0]*d[1]])
        matrix.append([0, 0, 0, d[0], d[1], 1, -s[1]*d[0], -s[1]*d[1]])
    A = np.array(matrix, dtype=float)
    B = np.array([p for pair in src for p in pair], dtype=float)
    res = np.linalg.solve(A, B)
    return tuple(res.flatten())
