"""
image_effects.py
Ken Burns effect — smooth pan & zoom on SHARP full-screen product image.
The image stays crisp throughout, camera movement creates dynamic feel.
Each variant gets a different pan/zoom direction for uniqueness.
"""
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw


# ─── 7 Ken Burns motion presets ───
# Each preset: (start_crop, end_crop) as (left%, top%, right%, bottom%)
# Video smoothly interpolates between start and end over duration

KENBURNS_PRESETS = [
    # 0: Zoom in from full → center crop
    {'start': (0.0, 0.0, 1.0, 1.0), 'end': (0.15, 0.10, 0.85, 0.90)},
    # 1: Pan left to right
    {'start': (0.0, 0.05, 0.75, 0.95), 'end': (0.25, 0.05, 1.0, 0.95)},
    # 2: Pan right to left
    {'start': (0.25, 0.05, 1.0, 0.95), 'end': (0.0, 0.05, 0.75, 0.95)},
    # 3: Zoom out from center → full
    {'start': (0.2, 0.15, 0.8, 0.85), 'end': (0.0, 0.0, 1.0, 1.0)},
    # 4: Pan down slowly
    {'start': (0.05, 0.0, 0.95, 0.75), 'end': (0.05, 0.25, 0.95, 1.0)},
    # 5: Pan up slowly (TT variant)
    {'start': (0.05, 0.25, 0.95, 1.0), 'end': (0.05, 0.0, 0.95, 0.75)},
    # 6: Diagonal zoom — top-left to center (FB variant)
    {'start': (0.0, 0.0, 0.80, 0.80), 'end': (0.10, 0.10, 0.90, 0.90)},
]

# Per-variant light color grade (subtle, not overwhelming)
VARIANT_GRADES = [
    {'brightness': 1.05, 'contrast': 1.10, 'saturation': 1.05},  # 0: Slightly vivid
    {'brightness': 0.95, 'contrast': 1.15, 'saturation': 0.90},  # 1: Moody/dark
    {'brightness': 1.10, 'contrast': 1.05, 'saturation': 1.15},  # 2: Vibrant
    {'brightness': 1.00, 'contrast': 1.20, 'saturation': 1.00},  # 3: High contrast
    {'brightness': 1.08, 'contrast': 1.00, 'saturation': 0.80},  # 4: Desaturated
    {'brightness': 1.02, 'contrast': 1.10, 'saturation': 1.20},  # 5: Super saturated
    {'brightness': 1.05, 'contrast': 1.08, 'saturation': 1.10},  # 6: Balanced warm
]


def color_grade(img, variant_index):
    """Apply subtle color grading per variant for copyright differentiation."""
    vi = variant_index % len(VARIANT_GRADES)
    grade = VARIANT_GRADES[vi]
    
    result = img
    if grade['brightness'] != 1.0:
        result = ImageEnhance.Brightness(result).enhance(grade['brightness'])
    if grade['contrast'] != 1.0:
        result = ImageEnhance.Contrast(result).enhance(grade['contrast'])
    if grade['saturation'] != 1.0:
        result = ImageEnhance.Color(result).enhance(grade['saturation'])
    
    return result


def prepare_kenburns_image(img_path, variant_index, target_w=1080, target_h=1920):
    """
    Prepare a SHARP product image sized for Ken Burns cropping.
    Returns a large PIL Image (bigger than target) that will be cropped during playback.
    Uses aggressive upscaling and multi-pass sharpening for maximum clarity.
    """
    img = Image.open(img_path).convert('RGB')
    orig_w, orig_h = img.size
    
    # ── Step 1: Upscale small images for clarity ──
    # Target minimum: 1620px (1.5× video width) on smallest dimension
    min_dim = min(orig_w, orig_h)
    if min_dim < 1620:
        scale = max(2.0, 1620 / min_dim)
        img = img.resize((int(orig_w * scale), int(orig_h * scale)), Image.LANCZOS)
        orig_w, orig_h = img.size
    
    # ── Step 2: Multi-pass sharpen the source image ──
    img = ImageEnhance.Sharpness(img).enhance(1.5)   # Increased from 1.3
    img = img.filter(ImageFilter.DETAIL)               # Enhance fine details
    
    # ── Step 3: Create oversized canvas (1.5x target) for pan room ──
    canvas_w = int(target_w * 1.5)
    canvas_h = int(target_h * 1.5)
    
    # Resize image to COVER the canvas (no black bars)
    canvas_aspect = canvas_w / canvas_h
    img_aspect = orig_w / orig_h
    
    if img_aspect > canvas_aspect:
        # Image is wider — fit height, let width overflow
        new_h = canvas_h
        new_w = int(orig_w * (canvas_h / orig_h))
    else:
        # Image is taller — fit width, let height overflow
        new_w = canvas_w
        new_h = int(orig_h * (canvas_w / orig_w))
    
    img_resized = img.resize((new_w, new_h), Image.LANCZOS)
    
    # Center-crop to canvas size (instead of padding with black)
    crop_x = (new_w - canvas_w) // 2
    crop_y = (new_h - canvas_h) // 2
    canvas = img_resized.crop((crop_x, crop_y, crop_x + canvas_w, crop_y + canvas_h))
    
    # ── Step 4: Apply color grade per variant ──
    canvas = color_grade(canvas, variant_index)
    
    # ── Step 5: Final sharpen + unsharp mask for razor clarity ──
    canvas = canvas.filter(ImageFilter.SHARPEN)
    canvas = canvas.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))
    
    return canvas


def make_kenburns_frame(canvas_img, t, duration, preset, target_w=1080, target_h=1920):
    """
    Generate a single frame at time t for Ken Burns effect.
    Smoothly interpolates crop window from start to end over duration.
    Returns numpy array (H, W, 3).
    """
    progress = min(t / max(duration, 0.01), 1.0)
    # Ease in-out for smoother motion
    progress = 0.5 * (1 - np.cos(np.pi * progress))
    
    cw, ch = canvas_img.size
    
    s = preset['start']
    e = preset['end']
    
    # Interpolate crop coordinates
    left = int(cw * (s[0] + (e[0] - s[0]) * progress))
    top = int(ch * (s[1] + (e[1] - s[1]) * progress))
    right = int(cw * (s[2] + (e[2] - s[2]) * progress))
    bottom = int(ch * (s[3] + (e[3] - s[3]) * progress))
    
    # Ensure minimum crop size
    min_w = target_w // 2
    min_h = target_h // 2
    if right - left < min_w:
        right = left + min_w
    if bottom - top < min_h:
        bottom = top + min_h
    
    # Clamp to canvas bounds
    left = max(0, left)
    top = max(0, top)
    right = min(cw, right)
    bottom = min(ch, bottom)
    
    # Crop and resize to target with LANCZOS (high quality)
    cropped = canvas_img.crop((left, top, right, bottom))
    frame = cropped.resize((target_w, target_h), Image.LANCZOS)
    
    return np.array(frame)


def get_preset(variant_index):
    """Get Ken Burns motion preset for a variant."""
    return KENBURNS_PRESETS[variant_index % len(KENBURNS_PRESETS)]
