"""
generate_video_yt_short.py
YouTube Shorts: 45-50s DYNAMIC product review.

Architecture (per instruksi_upgrade_system.md Bagian 5):
  Uses PRE-COMPOSITED images (product + photo background) from image_compositor.py
  Each scene uses a DIFFERENT composite image, animated with:
    - Ken Burns effect (zoom + pan)
    - Parallax (via depth map from depth_analyzer.py)
    - Zoom punch transitions between scenes
  Text overlays + SFX on top.

Scenes:
  Hook(0-3s) -> Hero(3-12s) -> Features(12-30s) -> Proof(30-40s) -> CTA(40-50s)
"""
import json
import os
import sys
import random
import datetime
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from moviepy import (VideoClip, ImageClip, AudioFileClip,
                     CompositeAudioClip, afx, concatenate_audioclips)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from engine.modules.category_router import (
    get_category, get_accent_color, get_copywriting,
    get_channel_name, get_channel_motto, VIDEO_DURATION
)
from engine.modules.video_effects import (
    render_text_image, paste_overlay_on_frame,
    text_slide_up, ease_out_back, ease_out_cubic,
    create_rating_stars, create_price_display, create_chat_bubble,
    create_count_up_text, create_blinking_label, create_simple_price,
    draw_frame_border, slide_element_x, sway_x,
    render_outline_text, create_plain_gradient
)
from engine.modules.sound_manager import get_sfx_path, init_sounds
from engine.modules.audio_normalizer import prepare_music, prepare_sfx, get_ffmpeg_audio_params, find_music_file, get_voice_volumes

W, H = 1080, 1920
COMPOSITES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'composites')
DEPTH_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'depth_maps')


def _load_composites(produk_id, category='home', count=5):
    """Generate FRESH composite images every run.
    Deletes old cached composites to prevent duplicate content detection."""
    import glob

    # CLEANUP: delete old cached composites for this product
    prod_dir = os.path.join(COMPOSITES_DIR, produk_id)
    if os.path.isdir(prod_dir):
        old = glob.glob(os.path.join(prod_dir, '*.png')) + glob.glob(os.path.join(prod_dir, '*.jpg'))
        for f in old:
            try: os.remove(f)
            except Exception: pass
        if old:
            print(f"    [CLEANUP] Deleted {len(old)} old composites from {produk_id}/")
    # Also clean flat naming
    flat_old = glob.glob(os.path.join(COMPOSITES_DIR, f"{produk_id}_composite_*.png"))
    for f in flat_old:
        try: os.remove(f)
        except Exception: pass

    # ALWAYS generate fresh composites (varied backgrounds each run)
    composites = _generate_fallback_composites(produk_id, category, count)

    # Ensure we have at least 'count' composites (duplicate if needed)
    while len(composites) < count:
        composites.append(composites[len(composites) % max(1, len(composites))].copy())

    # TRUE random shuffle (no static seed — different order every run)
    random.shuffle(composites)

    return composites


def _generate_fallback_composites(produk_id, category, count=5):
    """Product image FILLS entire frame (cover mode) — sesuai acuan video.
    
    Layout stack:
      Layer 0: Blurred product image (full screen — bokeh effect)
      Layer 1: Sharp product image (cover — fills frame area)
      Layer 2: Frame border + text added later in make_frame()
    """
    from engine.modules.premium_background import create_premium_background, add_product_shadow

    composites = []

    img_path = None
    for ext in ['png', 'jpg', 'webp']:
        p = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', f"{produk_id}.{ext}")
        if os.path.exists(p):
            img_path = p
            break

    product_img = None
    is_transparent = False
    if img_path:
        try:
            product_img = Image.open(img_path)
            if product_img.mode == 'RGBA':
                is_transparent = True
            else:
                product_img = product_img.convert('RGB')
            pw, ph = product_img.size
            if pw < 50 or ph < 50:
                product_img = None
        except Exception:
            product_img = None

    if product_img is None:
        print(f"    [WARN] No valid image for {produk_id}")
        for i in range(count):
            bg = create_premium_background(W, H, category=category, variant=i)
            composites.append(np.array(bg))
        return composites

    # Auto-trim white borders from Shopee images
    from engine.modules.image_utils import auto_trim_whitespace
    product_img = auto_trim_whitespace(product_img, is_transparent)
    if product_img.mode == 'RGBA':
        product_img = product_img.convert('RGB')

    pw, ph = product_img.size

    # COVER MODE: fill entire canvas
    cover_scale = max(W / pw, H / ph)
    cover_w, cover_h = int(pw * cover_scale), int(ph * cover_scale)
    img_cover = product_img.resize((cover_w, cover_h), Image.LANCZOS)
    cx = (cover_w - W) // 2
    cy = (cover_h - H) // 2
    img_cover = img_cover.crop((cx, cy, cx + W, cy + H))

    # Blurred edges outside pigura (bokeh sesuai acuan)
    img_blur = img_cover.filter(ImageFilter.GaussianBlur(radius=25))
    blur_arr = np.array(img_blur).astype(np.float32) * 0.7
    img_blur = Image.fromarray(np.clip(blur_arr, 0, 255).astype(np.uint8))

    frame_margin = 22

    for i in range(count):
        canvas = img_blur.copy()
        inner_m = frame_margin + 4
        inner_w = W - inner_m * 2
        inner_h = H - inner_m * 2
        inner_scale = max(inner_w / pw, inner_h / ph)
        fill_w = int(pw * inner_scale)
        fill_h = int(ph * inner_scale)
        img_fill = product_img.resize((fill_w, fill_h), Image.LANCZOS)
        fx = (fill_w - inner_w) // 2
        fy = (fill_h - inner_h) // 2
        img_fill = img_fill.crop((fx, fy, fx + inner_w, fy + inner_h))
        canvas.paste(img_fill, (inner_m, inner_m))
        composites.append(np.array(canvas))

    return composites


def _make_gradient_short(accent, index):
    """Last-resort gradient for YT Short."""
    grad = np.zeros((H, W, 3), dtype=np.uint8)
    hue_shift = index * 15
    top_color = tuple(min(255, max(0, c + hue_shift - 20)) for c in accent)
    bot_color = (15, 10, 20)
    for y in range(H):
        r = y / H
        for c in range(3):
            grad[y, :, c] = int(top_color[c] * (1 - r) + bot_color[c] * r)
    return Image.fromarray(grad)


def _ken_burns(composite_arr, t, duration, direction='zoom_in'):
    """Apply Ken Burns effect (zoom + pan) to a composite image.
    Returns a (H, W, 3) numpy frame."""
    h, w = composite_arr.shape[:2]
    progress = t / max(duration, 0.01)
    progress = min(1.0, max(0.0, progress))

    if direction == 'zoom_in':
        start_scale, end_scale = 1.0, 1.15
        start_cx, start_cy = 0.5, 0.5
        end_cx, end_cy = 0.48, 0.45
    elif direction == 'zoom_out':
        start_scale, end_scale = 1.15, 1.0
        start_cx, start_cy = 0.48, 0.45
        end_cx, end_cy = 0.5, 0.5
    elif direction == 'pan_left':
        start_scale, end_scale = 1.10, 1.10
        start_cx, start_cy = 0.55, 0.48
        end_cx, end_cy = 0.45, 0.48
    elif direction == 'pan_right':
        start_scale, end_scale = 1.10, 1.10
        start_cx, start_cy = 0.45, 0.48
        end_cx, end_cy = 0.55, 0.48
    elif direction == 'pan_up':
        start_scale, end_scale = 1.10, 1.10
        start_cx, start_cy = 0.5, 0.55
        end_cx, end_cy = 0.5, 0.42
    else:  # pan_down
        start_scale, end_scale = 1.10, 1.10
        start_cx, start_cy = 0.5, 0.42
        end_cx, end_cy = 0.5, 0.55

    # Smooth easing
    ease_p = 0.5 * (1 - math.cos(progress * math.pi))

    scale = start_scale + (end_scale - start_scale) * ease_p
    cx = start_cx + (end_cx - start_cx) * ease_p
    cy = start_cy + (end_cy - start_cy) * ease_p

    # Calculate crop region
    crop_w = int(w / scale)
    crop_h = int(h / scale)
    x1 = int(cx * w - crop_w / 2)
    y1 = int(cy * h - crop_h / 2)

    # Clamp
    x1 = max(0, min(x1, w - crop_w))
    y1 = max(0, min(y1, h - crop_h))
    crop_w = min(crop_w, w - x1)
    crop_h = min(crop_h, h - y1)

    if crop_w < 1 or crop_h < 1:
        return composite_arr

    cropped = composite_arr[y1:y1 + crop_h, x1:x1 + crop_w]
    result = Image.fromarray(cropped).resize((W, H), Image.LANCZOS)
    return np.array(result)


def _get_composite_frame(composites, t, cycle=10, dissolve_dur=0.5):
    """Static composite with cross-dissolve. Product stays fixed in frame."""
    idx = int(t / cycle) % len(composites)
    next_idx = (idx + 1) % len(composites)
    cycle_t = t % cycle
    if cycle_t > cycle - dissolve_dur:
        progress = (cycle_t - (cycle - dissolve_dur)) / dissolve_dur
        ease = progress * progress * (3 - 2 * progress)
        blended = (composites[idx].astype(float) * (1 - ease) + 
                   composites[next_idx].astype(float) * ease)
        return np.clip(blended, 0, 255).astype(np.uint8)
    return composites[idx]

def _zoom_punch_transition(img1_arr, img2_arr, t, duration=0.4):
    """Zoom punch transition between two composite images."""
    progress = min(1.0, t / duration)
    # img1 zooms in and fades, img2 appears from zoom out
    if progress < 0.5:
        # Zoom into img1
        scale = 1.0 + progress * 2 * 0.3
        p = progress * 2
        result = _ken_burns(img1_arr, p * 0.5, 1.0, 'zoom_in')
        # Fade
        fade = int((1.0 - progress * 2) * 255)
        result = np.clip(result * (fade / 255.0), 0, 255).astype(np.uint8)
        return result
    else:
        # Zoom out from img2
        p = (progress - 0.5) * 2
        scale = 1.3 - p * 0.3
        ease_p = ease_out_cubic(p)
        result = _ken_burns(img2_arr, ease_p * 0.2, 1.0, 'zoom_out')
        # Fade in
        fade = int(p * 255)
        result = np.clip(result * (fade / 255.0), 0, 255).astype(np.uint8)
        return result


def _load_font(bold=False):
    """Load font, with fallback."""
    try:
        from font_helper import get_font, get_font_bold
        path = get_font_bold() if bold else get_font()
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    for candidate in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                      "arial.ttf"]:
        if os.path.exists(candidate):
            return candidate
    return None


def generate_shorts(queue_file, output_dir):
    """Generate YouTube Shorts using PRE-COMPOSITED images with Ken Burns animation."""
    print(f"Generating YouTube Shorts from {queue_file}...")

    if not os.path.exists(queue_file):
        print(f"Queue not found: {queue_file}")
        return

    init_sounds()

    os.makedirs(os.path.join(output_dir, "yt"), exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")

    jobs = []
    with open(queue_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                jobs.append(json.loads(line))

    short_jobs = [j for j in jobs if j.get('video_type', 'short') in ('short', '')]
    if not short_jobs:
        short_jobs = jobs

    font_path = _load_font(bold=False)
    font_bold = _load_font(bold=True)

    dur_cfg = VIDEO_DURATION['yt_short']
    target_dur = random.randint(dur_cfg['min'], dur_cfg['max'])

    for job in short_jobs:
        produk_id = job['produk_id']
        acct_id = job.get('account_id', 'yt_1')
        acct_num = int(acct_id.split('_')[1]) if '_' in acct_id else 1
        category = get_category(acct_id)
        channel = get_channel_name(acct_id)
        accent = get_accent_color(category)

        print(f"\nRendering YT Short for {produk_id} ({acct_id}, {category})...")

        # Skip if Shorts already extracted from Long-form
        existing_short = os.path.join(output_dir, "yt",
                                       f"{today}_{produk_id}_v{acct_num}_yt.mp4")
        if os.path.exists(existing_short):
            print(f"  [SKIP] Shorts already exists: {os.path.basename(existing_short)}")
            continue

        hooks = get_copywriting(category, 'hooks')
        ctas = get_copywriting(category, 'cta')
        hook_text = job.get('hook', random.choice(hooks) if hooks else 'Cek ini!')
        nama = job.get('nama', produk_id)
        from engine.modules.image_utils import clean_product_name
        nama = clean_product_name(nama)
        harga = job.get('harga', '')
        desc = job.get('deskripsi_singkat', '')
        cta_text = job.get('cta', random.choice(ctas) if ctas else 'Link di deskripsi!')
        rating_val = round(random.uniform(4.5, 4.9), 1)
        sold_count = random.randint(500, 9999)

        total_dur = target_dur
        
        # === DYNAMIC FLOW STAGES (YT Short 45-50s) ===
        S1_END = 5.0     # Nama + teaser
        S2_END = 7.0     # Gambar masuk
        S3_END = 25.0    # Gambar goyang + info
        S4_END = 27.0    # Gambar keluar
        S5_END = 38.0    # Fitur/review text
        S6_END = 39.5    # Transition
        # S7 = 39.5 - total_dur: CTA
        
        SLIDE_DUR = 0.8
        PROD_SLIDE = 1.5  # Slower product entry

        try:
            composites = _load_composites(produk_id, category, count=5)
            print(f"  [OK] Loaded {len(composites)} composites")

            prod_img_pil = None
            for ext in ['png', 'jpg', 'webp']:
                p = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', f"{produk_id}.{ext}")
                if os.path.exists(p):
                    prod_img_pil = Image.open(p)
                    break
            
            if prod_img_pil:
                from engine.modules.image_utils import auto_trim_whitespace
                is_transp = prod_img_pil.mode == 'RGBA'
                if not is_transp:
                    prod_img_pil = prod_img_pil.convert('RGB')
                prod_img_pil = auto_trim_whitespace(prod_img_pil, is_transp)
                pw, ph = prod_img_pil.size
                prod_scale = min(W / pw, H / ph) * 0.90
                prod_w = int(pw * prod_scale)
                prod_h = int(ph * prod_scale)
                prod_img_pil = prod_img_pil.resize((prod_w, prod_h), Image.LANCZOS)
                if not is_transp:
                    prod_img_pil = prod_img_pil.convert('RGBA')
            
            border_color = tuple(min(255, c + 60) for c in accent)

            # Pure visual — NO text overlay, product image speaks for itself
            # All info (nama, harga, link) goes in description + pinned comment

            def make_frame(t):
                frame = _get_composite_frame(composites, t, cycle=10)
                frame = draw_frame_border(frame, accent_color=border_color, t=t)
                return frame

            video = VideoClip(make_frame, duration=total_dur).with_fps(24)

            audio_clips = []
            vo_vol, music_vol = get_voice_volumes(acct_id)

            music_dir = os.path.join(output_dir, "yt")
            music_path, music_tier = find_music_file(music_dir, produk_id, acct_id, category)
            if music_path:
                music = prepare_music(AudioFileClip(music_path), total_dur, music_vol=music_vol)
                audio_clips.append(music)



            # Voiceover
            vo_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers', produk_id, 'yt_short')
            vo_stages = [('hook', 0.0), ('hero', S1_END), ('feature', S4_END), ('cta', S6_END)]
            for idx, (stage_id, start_time) in enumerate(vo_stages):
                vo_path = os.path.join(vo_dir, f"vo_{stage_id}.mp3")
                if os.path.exists(vo_path) and start_time < total_dur:
                    try:
                        vo = AudioFileClip(vo_path)
                        if idx + 1 < len(vo_stages):
                            max_dur = vo_stages[idx + 1][1] - start_time - 0.3
                        else:
                            max_dur = total_dur - start_time - 0.2
                        if max_dur > 0.5 and vo.duration > max_dur:
                            vo = vo.subclipped(0, max_dur)
                        from engine.modules.audio_normalizer import normalize_audio_clip
                        vo = normalize_audio_clip(vo)
                        vo = vo.with_effects([afx.MultiplyVolume(vo_vol)])
                        vo = vo.with_start(start_time)
                        audio_clips.append(vo)
                    except Exception:
                        pass

            if audio_clips:
                try:
                    video = video.with_audio(CompositeAudioClip(audio_clips))
                except Exception as e:
                    print(f"  [WARN] Audio failed: {e}")

            out_file = f"{today}_{produk_id}_v{acct_num}_yt.mp4"
            out_path = os.path.join(output_dir, "yt", out_file)
            audio_params = get_ffmpeg_audio_params()
            video.write_videofile(out_path, fps=24, codec='libx264',
                                preset='ultrafast', logger=None,
                                **audio_params)
            print(f"  [OK] Short: {out_file} ({total_dur}s)")
            video.close()

        except Exception as e:
            import traceback
            print(f"  [FAIL] Short render: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    generate_shorts("engine/queue/yt_queue.jsonl", "engine/output")
