"""
video_effects.py
Animation engine for CapCut-style dynamic videos.

Provides:
  - Product entry animations (slide-up, scale-up, bounce, fade-slide)
  - Text animations (typewriter, slide-up, scale, pop)
  - Transitions (zoom-punch, slide, flash-cut, whip)
  - Helpers (blur BG, dim BG, vignette, price strikethrough, rating stars,
    count-up, chat bubbles, blinking text)

All built with MoviePy + PIL + NumPy â€” no external dependencies.
"""
import random
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1080, 1920


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  EASING FUNCTIONS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def ease_out_back(t):
    """Overshoot then settle â€” bouncy feel."""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)

def ease_out_cubic(t):
    return 1 - pow(1 - t, 3)

def ease_out_elastic(t):
    if t == 0 or t == 1:
        return t
    return pow(2, -10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi) / 3) + 1

def ease_in_out_quad(t):
    return 2 * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 2) / 2


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  BACKGROUND EFFECTS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def blur_frame(frame_arr, radius=5):
    """Apply Gaussian blur to a video frame."""
    img = Image.fromarray(frame_arr)
    img = img.filter(ImageFilter.GaussianBlur(radius))
    return np.array(img)

def dim_frame(frame_arr, factor=0.6):
    """Dim brightness of a frame (0.0=black, 1.0=original)."""
    return np.clip(frame_arr.astype(np.float32) * factor, 0, 255).astype(np.uint8)

def process_bg_frame(frame_arr, blur_radius=5, dim_factor=0.6):
    """Blur + dim a background video frame."""
    frame = blur_frame(frame_arr, blur_radius)
    frame = dim_frame(frame, dim_factor)
    return frame

def create_vignette_overlay(size=(W, H), strength=0.7):
    """Create a vignette (dark edges) overlay as RGBA array."""
    w, h = size
    vig = np.zeros((h, w, 4), dtype=np.uint8)
    cx, cy = w / 2, h / 2
    max_dist = math.sqrt(cx**2 + cy**2)
    for y in range(0, h, 4):  # Sample every 4 pixels for speed
        for x in range(0, w, 4):
            dist = math.sqrt((x - cx)**2 + (y - cy)**2) / max_dist
            alpha = int(min(255, dist ** 1.5 * 255 * strength))
            vig[y:y+4, x:x+4, 3] = alpha
    return vig


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  PRODUCT ENTRY ANIMATIONS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def product_slide_up(product_rgba, canvas_size, target_pos, t, anim_dur=0.6):
    """Product slides up from below screen into target position."""
    progress = min(t / anim_dur, 1.0)
    ease = ease_out_back(progress)

    tx, ty = target_pos
    start_y = canvas_size[1] + 100  # Start below screen
    current_y = int(start_y + (ty - start_y) * ease)

    return tx, current_y, 1.0  # x, y, scale


def product_scale_up(product_rgba, canvas_size, target_pos, t, anim_dur=0.5):
    """Product scales from 0 to full size with slight bounce."""
    progress = min(t / anim_dur, 1.0)
    scale = ease_out_back(progress)
    scale = max(0.01, min(1.2, scale))  # Clamp to avoid issues

    return target_pos[0], target_pos[1], scale


def product_fade_slide(product_rgba, canvas_size, target_pos, t, anim_dur=0.6,
                       from_side='left'):
    """Product fades in while sliding from side."""
    progress = min(t / anim_dur, 1.0)
    ease = ease_out_cubic(progress)

    tx, ty = target_pos
    offset = 200 if from_side == 'left' else -200
    start_x = tx + offset
    current_x = int(start_x + (tx - start_x) * ease)
    opacity = progress  # Linear fade

    return current_x, ty, opacity


def get_random_product_anim():
    """Return a random product animation function."""
    return random.choice([product_slide_up, product_scale_up])


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  TEXT RENDERING + ANIMATIONS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def render_text_image(text, font_path, font_size, text_color, bg_color,
                      max_width=1000, padding=20, radius=14, style=None):
    """Render text with varied visual styles. Returns PIL RGBA Image.
    
    Styles:
      'gradient_pill' â€” Gradient background pill shape
      'glass' â€” Frosted glass with border
      'glow' â€” Dark bg with text glow/outline
      'clean' â€” Modern minimal with accent left bar
      None â€” Random selection for variety
    """
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()

    # Word wrap using font.getlength for accurate width
    words = text.split()
    lines, cur = [], ""
    dummy = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    wrap_width = max_width - padding * 2
    for w in words:
        test = f"{cur} {w}".strip()
        try:
            tw_test = font.getlength(test)
        except AttributeError:
            bb = dummy.textbbox((0, 0), test, font=font)
            tw_test = bb[2] - bb[0]
        if tw_test > wrap_width:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    if not lines:
        lines = [text]

    # Measure each line using getlength (more reliable than textbbox for centering)
    line_widths = []
    line_heights = []
    for l in lines:
        bb = dummy.textbbox((0, 0), l, font=font)
        line_heights.append(bb[3] - bb[1])
        try:
            line_widths.append(int(font.getlength(l)))
        except AttributeError:
            line_widths.append(bb[2] - bb[0])

    spacing = max(24, int(font_size * 0.7))  # 70% of font size = generous spacing
    th = sum(line_heights) + (len(lines) - 1) * spacing
    tw = max(line_widths) if line_widths else 80

    pad = padding + 16  # Generous padding for breathing room
    iw, ih = tw + pad * 2, th + pad * 2

    # Pick style
    if style is None:
        style = random.choice(['gradient_pill', 'glass', 'glow', 'clean'])

    img = Image.new('RGBA', (iw, ih), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Extract bg color components
    if isinstance(bg_color, tuple):
        br, bg_g, bb_c = bg_color[0], bg_color[1], bg_color[2]
        ba = bg_color[3] if len(bg_color) > 3 else 220
    else:
        br, bg_g, bb_c, ba = 30, 30, 50, 220

    if style == 'gradient_pill':
        # Horizontal gradient background
        for x in range(iw):
            ratio = x / max(iw, 1)
            r = int(br * (1 - ratio) + min(br + 40, 255) * ratio)
            g = int(bg_g * (1 - ratio) + max(bg_g - 20, 0) * ratio)
            b = int(bb_c * (1 - ratio) + min(bb_c + 30, 255) * ratio)
            d.line([(x, 0), (x, ih)], fill=(r, g, b, ba))
        # Round corners by masking
        mask = Image.new('L', (iw, ih), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle([0, 0, iw, ih], radius=radius + 4, fill=255)
        img.putalpha(mask)
        d = ImageDraw.Draw(img)  # Re-init draw after alpha change

    elif style == 'glass':
        # Frosted glass â€” semi-transparent with white border
        d.rounded_rectangle([0, 0, iw, ih], radius=radius,
                           fill=(br, bg_g, bb_c, int(ba * 0.6)))
        # White border for glass effect
        d.rounded_rectangle([0, 0, iw, ih], radius=radius,
                           outline=(255, 255, 255, 80), width=2)
        # Inner lighter line
        d.rounded_rectangle([3, 3, iw - 3, ih - 3], radius=max(radius - 3, 4),
                           outline=(255, 255, 255, 40), width=1)

    elif style == 'glow':
        # Dark background with text glow
        d.rounded_rectangle([0, 0, iw, ih], radius=radius,
                           fill=(15, 12, 20, int(ba * 0.85)))
        # Subtle inner shadow
        d.rounded_rectangle([2, 2, iw - 2, ih - 2], radius=max(radius - 2, 4),
                           outline=(br, bg_g, bb_c, 60), width=2)

    elif style == 'clean':
        # Modern minimal â€” dark bg with accent left bar
        d.rounded_rectangle([0, 0, iw, ih], radius=radius,
                           fill=(20, 18, 28, int(ba * 0.9)))
        # Accent left bar
        d.rounded_rectangle([0, 6, 5, ih - 6], radius=3,
                           fill=(br, bg_g, bb_c, 255))

    else:
        # Fallback â€” original plain style
        d.rounded_rectangle([0, 0, iw, ih], radius=radius, fill=bg_color)

    # === Draw text â€” centered using midpoint approach ===
    cy = (ih - th) // 2  # Start Y for vertical centering
    center_x = iw // 2   # Horizontal center of pill

    for i, line in enumerate(lines):
        draw_x = center_x - line_widths[i] // 2  # Manual center: midpoint - half width

        # Text outline (dark border for readability)
        outline_color = (0, 0, 0, 200)
        for ox, oy in [(-2,-2),(2,-2),(-2,2),(2,2),(-1,0),(1,0),(0,-1),(0,1)]:
            d.text((draw_x + ox, cy + oy), line, fill=outline_color, font=font)

        # Glow for glow style
        if style == 'glow':
            glow_color = (br, bg_g, bb_c, 120)
            for ox, oy in [(-3,-3),(3,-3),(-3,3),(3,3)]:
                d.text((draw_x + ox, cy + oy), line, fill=glow_color, font=font)

        # Main text
        d.text((draw_x, cy), line, fill=text_color, font=font)
        cy += line_heights[i] + spacing

    return img


def text_slide_up(text_img, canvas_h, target_y, t, anim_dur=0.35):
    """Text slides up from below into position."""
    progress = min(t / anim_dur, 1.0)
    ease = ease_out_cubic(progress)
    start_y = canvas_h + 50
    return int(start_y + (target_y - start_y) * ease)


def text_scale_pop(t, anim_dur=0.3):
    """Returns scale factor for pop-in effect."""
    progress = min(t / anim_dur, 1.0)
    return ease_out_back(progress)


def text_typewriter_mask(text_img, t, total_chars, char_delay=0.05):
    """Returns a cropped version showing only revealed characters.

    This is a simple left-crop approximation of typewriter effect.
    """
    w, h = text_img.size
    chars_shown = int(t / char_delay)
    ratio = min(chars_shown / max(total_chars, 1), 1.0)
    crop_w = max(1, int(w * ratio))
    return text_img.crop((0, 0, crop_w, h))


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  TRANSITION EFFECTS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def transition_flash(frame_a, frame_b, t, dur=0.15):
    """White flash cut between scenes."""
    progress = t / dur
    if progress < 0.4:
        # Flash to white
        blend = progress / 0.4
        white = np.full_like(frame_a, 255)
        return np.clip(frame_a * (1 - blend) + white * blend, 0, 255).astype(np.uint8)
    elif progress < 0.6:
        return np.full_like(frame_a, 255, dtype=np.uint8)
    else:
        # Fade from white to B
        blend = (progress - 0.6) / 0.4
        white = np.full_like(frame_b, 255)
        return np.clip(white * (1 - blend) + frame_b * blend, 0, 255).astype(np.uint8)


def transition_zoom_punch(frame_a, frame_b, t, dur=0.25):
    """Zoom into A, then cut to B zoomed out."""
    progress = t / dur
    if progress < 0.5:
        # Zoom into A
        zoom = 1.0 + progress * 0.6  # Up to 1.3x
        return _zoom_frame(frame_a, zoom)
    else:
        # B starts zoomed in, returns to normal
        zoom = 1.3 - (progress - 0.5) * 0.6
        return _zoom_frame(frame_b, max(1.0, zoom))


def transition_slide_h(frame_a, frame_b, t, dur=0.3):
    """Horizontal slide â€” A slides out left, B slides in from right."""
    progress = min(t / dur, 1.0)
    ease = ease_in_out_quad(progress)
    h, w = frame_a.shape[:2]
    offset = int(w * ease)

    result = np.zeros_like(frame_a)
    if offset < w:
        result[:, :w-offset] = frame_a[:, offset:]
    if offset > 0:
        result[:, max(0, w-offset):] = frame_b[:, :min(offset, w)]
    return result


def _zoom_frame(frame, zoom):
    """Crop center of frame at given zoom level."""
    h, w = frame.shape[:2]
    new_h, new_w = int(h / zoom), int(w / zoom)
    top = (h - new_h) // 2
    left = (w - new_w) // 2
    cropped = frame[top:top+new_h, left:left+new_w]
    img = Image.fromarray(cropped)
    img = img.resize((w, h), Image.LANCZOS)
    return np.array(img)


def get_random_transition():
    """Return a random transition function."""
    return random.choice([transition_flash, transition_zoom_punch, transition_slide_h])


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  SPECIAL ELEMENTS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def create_rating_stars(rating, font_path, size=48, animated_t=None, total_dur=1.5):
    """Create rating stars using PIL shapes (no Unicode = no garbled text)."""
    full = int(rating)

    if animated_t is not None:
        stars_to_show = min(5, int(animated_t / total_dur * 5) + 1)
    else:
        stars_to_show = 5

    star_size = max(20, size // 2)
    total_w = 5 * (star_size + 6) + 120
    total_h = star_size + 30

    img = Image.new('RGBA', (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background pill
    draw.rounded_rectangle([0, 0, total_w, total_h], radius=12, fill=(0, 0, 0, 180))

    # Draw filled circles as star indicators
    y_center = total_h // 2
    for i in range(5):
        x = 14 + i * (star_size + 6)
        if i < stars_to_show and i < full:
            draw.ellipse([x, y_center - star_size//2,
                         x + star_size, y_center + star_size//2],
                        fill=(255, 215, 0, 255))
        elif i < stars_to_show:
            draw.ellipse([x, y_center - star_size//2,
                         x + star_size, y_center + star_size//2],
                        outline=(255, 215, 0, 180), width=2)

    # Rating number
    try:
        font = ImageFont.truetype(font_path, size)
    except Exception:
        font = ImageFont.load_default()

    text_x = 14 + 5 * (star_size + 6) + 8
    text_y = (total_h - size) // 2
    draw.text((text_x, text_y), str(rating), fill=(255, 255, 200), font=font)

    return img


def create_price_display(old_price, new_price, font_path, accent_color,
                         t=None, anim_dur=1.0):
    """Create price strikethrough + promo price display."""
    w, h = 700, 200
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font_old = ImageFont.truetype(font_path, 36)
        font_new = ImageFont.truetype(font_path, 56)
    except Exception:
        font_old = ImageFont.load_default()
        font_new = font_old

    # Background
    draw.rounded_rectangle([0, 0, w, h], radius=16, fill=(0, 0, 0, 210))

    # Old price with strikethrough
    old_text = f"Rp {old_price}"
    bb_old = draw.textbbox((0, 0), old_text, font=font_old)
    old_w = bb_old[2] - bb_old[0]
    old_x = (w - old_w) // 2
    draw.text((old_x, 25), old_text, fill=(180, 180, 180), font=font_old)

    # Strikethrough line
    if t is None or t > anim_dur * 0.3:
        line_y = 25 + (bb_old[3] - bb_old[1]) // 2 + 5
        draw.line([(old_x - 5, line_y), (old_x + old_w + 5, line_y)],
                 fill=(255, 80, 80), width=3)

    # New price (appears after strikethrough)
    if t is None or t > anim_dur * 0.5:
        new_text = f"Rp {new_price}"
        bb_new = draw.textbbox((0, 0), new_text, font=font_new)
        new_w = bb_new[2] - bb_new[0]
        new_x = (w - new_w) // 2
        draw.text((new_x, 90), new_text, fill=(*accent_color, 255), font=font_new)

    return img


def create_chat_bubble(text, font_path, side='left', accent_color=(66, 133, 244)):
    """Create a review chat bubble that slides in from side."""
    max_w = 700
    padding = 18
    font_size = 32

    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()

    # Measure text using font.getlength
    dummy = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    words = text.split()
    lines, cur = [], ""
    wrap_width = max_w - padding * 3
    for word in words:
        test = f"{cur} {word}".strip()
        try:
            tw_test = font.getlength(test)
        except AttributeError:
            bb = dummy.textbbox((0, 0), test, font=font)
            tw_test = bb[2] - bb[0]
        if tw_test > wrap_width:
            if cur:
                lines.append(cur)
            cur = word
        else:
            cur = test
    if cur:
        lines.append(cur)
    if not lines:
        lines = [text]

    # Measure each line
    line_widths = []
    line_heights = []
    for l in lines:
        bb = dummy.textbbox((0, 0), l, font=font)
        line_heights.append(bb[3] - bb[1])
        try:
            line_widths.append(int(font.getlength(l)))
        except AttributeError:
            line_widths.append(bb[2] - bb[0])

    spacing = max(12, font_size // 3)  # Much better than spacing=6
    th = sum(line_heights) + (len(lines) - 1) * spacing
    tw = max(line_widths) if line_widths else 100

    bw = tw + padding * 3
    bh = th + padding * 2 + 16  # Extra room

    img = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Bubble background
    bg_color = (*accent_color, 200) if side == 'left' else (60, 60, 70, 200)
    d.rounded_rectangle([10, 0, bw, bh - 10], radius=16, fill=bg_color)

    # Avatar circle
    if side == 'left':
        d.ellipse([0, bh - 30, 28, bh - 2], fill=(200, 200, 200, 200))

    # Text — CENTERED horizontally, vertically centered in bubble
    cy = (bh - 10 - th) // 2  # center within bubble area (bh - 10 for avatar space)
    bubble_center_x = (10 + bw) // 2  # center of visible bubble area
    for i, line in enumerate(lines):
        draw_x = bubble_center_x - line_widths[i] // 2
        draw_x = max(draw_x, 14)  # Don't go past left edge
        # Outline for readability
        for ox, oy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
            d.text((draw_x + ox, cy + oy), line, fill=(0, 0, 0, 120), font=font)
        d.text((draw_x, cy), line, fill=(255, 255, 255), font=font)
        cy += line_heights[i] + spacing

    return img


def create_count_up_text(current_val, label, font_path, accent_color, font_size=44):
    """Create an animated number display (e.g. '1,234+ Terjual')."""
    text = f"{current_val:,}+ {label}"
    return render_text_image(text, font_path, font_size, (255, 255, 255),
                            (*accent_color, 210), max_width=800, padding=16)


def create_blinking_label(text, font_path, accent_color, t, blink_speed=0.5,
                          font_size=40, max_width=800):
    """Create text that blinks (opacity pulses)."""
    opacity = int(128 + 127 * math.sin(2 * math.pi * t / blink_speed))
    return render_text_image(text, font_path, font_size, (255, 255, 255),
                            (*accent_color, opacity), max_width=max_width, padding=14)


def create_simple_price(price_text, font_path, font_size=48, accent_color=(255, 64, 129)):
    """Create a simple price label (single price, no strikethrough)."""
    return render_text_image(price_text, font_path, font_size, (255, 255, 255),
                            (*accent_color, 220), max_width=800, padding=16)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  COMPOSITE HELPER
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def composite_product_on_frame(frame_arr, product_rgba, x, y, scale=1.0, opacity=1.0,
                                rotation=0, reflection=False):
    """Paste isolated product onto a video frame with professional compositing.
    
    Features:
      - Multi-layer shadow (tight + diffuse)
      - Subtle rotation for natural feel
      - Optional bottom reflection
      - Edge glow for depth
      - Color temperature matching to background
    """
    canvas = Image.fromarray(frame_arr).convert('RGBA')

    if scale != 1.0 and scale > 0.01:
        pw, ph = product_rgba.size
        new_w, new_h = max(1, int(pw * scale)), max(1, int(ph * scale))
        product = product_rgba.resize((new_w, new_h), Image.LANCZOS)
    else:
        product = product_rgba.copy()

    # â”€â”€ Subtle rotation for natural feel â”€â”€
    if rotation != 0:
        product = product.rotate(rotation, expand=True, resample=Image.BICUBIC,
                                fillcolor=(0, 0, 0, 0))

    alpha = product.split()[3]

    # â”€â”€ Multi-layer shadow for depth â”€â”€
    # Layer 1: Tight contact shadow (close, crisp)
    shadow1 = Image.new('RGBA', product.size, (0, 0, 0, 0))
    sa1 = Image.new('L', product.size, 0)
    sa1.paste(100, mask=alpha)
    shadow1.putalpha(sa1)
    shadow1 = shadow1.filter(ImageFilter.GaussianBlur(8))

    # Layer 2: Distant diffuse shadow (further, softer)
    shadow2 = Image.new('RGBA', product.size, (0, 0, 0, 0))
    sa2 = Image.new('L', product.size, 0)
    sa2.paste(50, mask=alpha)
    shadow2.putalpha(sa2)
    shadow2 = shadow2.filter(ImageFilter.GaussianBlur(25))

    # â”€â”€ Edge glow (subtle backlight) â”€â”€
    glow = Image.new('RGBA', product.size, (0, 0, 0, 0))
    glow_a = Image.new('L', product.size, 0)
    glow_a.paste(35, mask=alpha)
    glow.putalpha(glow_a)
    glow = glow.filter(ImageFilter.GaussianBlur(12))
    # Tint glow â€” sample background avg color
    bg_crop_x = max(0, min(x, canvas.width - 50))
    bg_crop_y = max(0, min(y, canvas.height - 50))
    try:
        bg_sample = canvas.crop((bg_crop_x, bg_crop_y,
                                min(bg_crop_x + 50, canvas.width),
                                min(bg_crop_y + 50, canvas.height)))
        avg_color = tuple(int(c) for c in np.array(bg_sample.convert('RGB')).mean(axis=(0, 1)))
    except:
        avg_color = (100, 100, 120)

    glow_arr = np.array(glow)
    glow_arr[:, :, 0] = np.clip(glow_arr[:, :, 0].astype(int) + avg_color[0] // 3, 0, 255)
    glow_arr[:, :, 1] = np.clip(glow_arr[:, :, 1].astype(int) + avg_color[1] // 3, 0, 255)
    glow_arr[:, :, 2] = np.clip(glow_arr[:, :, 2].astype(int) + avg_color[2] // 3, 0, 255)
    glow = Image.fromarray(glow_arr).convert('RGBA')

    # â”€â”€ Color temperature matching â”€â”€
    # Shift product colors slightly toward background tone
    prod_arr = np.array(product).astype(np.float32)
    tone_shift = np.array([avg_color[0] - 128, avg_color[1] - 128, avg_color[2] - 128]) * 0.08
    for c in range(3):
        prod_arr[:, :, c] = np.clip(prod_arr[:, :, c] + tone_shift[c], 0, 255)
    if opacity < 1.0:
        prod_arr[:, :, 3] = (prod_arr[:, :, 3] * opacity)
    product = Image.fromarray(prod_arr.astype(np.uint8)).convert('RGBA')

    # â”€â”€ Paste layers â”€â”€
    # Diffuse shadow (offset further)
    s2x, s2y = x + 18, y + 22
    if 0 <= s2x < canvas.width and 0 <= s2y < canvas.height:
        canvas.paste(shadow2, (s2x, s2y), shadow2)
    # Contact shadow
    s1x, s1y = x + 6, y + 8
    if 0 <= s1x < canvas.width and 0 <= s1y < canvas.height:
        canvas.paste(shadow1, (s1x, s1y), shadow1)
    # Edge glow
    gx, gy = x - 4, y - 4
    if 0 <= gx < canvas.width and 0 <= gy < canvas.height:
        canvas.paste(glow, (gx, gy), glow)
    # Product
    if 0 <= x < canvas.width and 0 <= y < canvas.height:
        canvas.paste(product, (x, y), product)

    # â”€â”€ Optional reflection (for CTA/overview scenes) â”€â”€
    if reflection and product.height > 50:
        refl = product.transpose(Image.FLIP_TOP_BOTTOM)
        refl_arr = np.array(refl).astype(np.float32)
        # Fade from top to bottom
        for row in range(refl_arr.shape[0]):
            fade = max(0, 1.0 - row / (refl_arr.shape[0] * 0.4))
            refl_arr[row, :, 3] *= fade * 0.25
        refl = Image.fromarray(refl_arr.astype(np.uint8)).convert('RGBA')
        ry = y + product.height + 5
        if ry < canvas.height:
            canvas.paste(refl, (x, ry), refl)

    return np.array(canvas.convert('RGB'))


def paste_overlay_on_frame(frame_arr, overlay_img, position, opacity=1.0):
    """Paste a PIL RGBA overlay onto a frame at position."""
    canvas = Image.fromarray(frame_arr).convert('RGBA')
    if opacity < 1.0:
        arr = np.array(overlay_img)
        arr[:, :, 3] = (arr[:, :, 3] * opacity).astype(np.uint8)
        overlay_img = Image.fromarray(arr).convert('RGBA')

    x, y = position
    x = max(0, min(x, canvas.width - 1))
    y = max(0, min(y, canvas.height - 1))
    canvas.paste(overlay_img, (x, y), overlay_img)
    return np.array(canvas.convert('RGB'))
