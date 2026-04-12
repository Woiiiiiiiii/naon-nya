"""
generate_video_yt_long.py
YouTube Long-form: 90-120s DETAILED product review.

Architecture (per instruksi_upgrade_system.md Bagian 5):
  Uses PRE-COMPOSITED images (product + photo background) from image_compositor.py
  7 scenes, each using a different composite image animated with Ken Burns + parallax.
  Text overlays + SFX on top.

7 Scenes:
  Hook(0-8s) -> Overview(8-25s) -> Detail1(25-45s) -> Detail2(45-65s)
  -> Comparison(65-80s) -> Verdict(80-95s) -> CTA(95-110s)

After rendering Long, AUTO-EXTRACTS a 45-50s Shorts version.
"""
import json
import os
import sys
import random
import datetime
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from moviepy import (VideoClip, ImageClip, AudioFileClip, CompositeAudioClip,
                     afx, concatenate_audioclips, concatenate_videoclips)

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

# Scene templates (3 variations for variety)
TEMPLATES = {
    'A': [
        {'id': 'hook',       's': 0,  'e': 8},
        {'id': 'overview',   's': 8,  'e': 25},
        {'id': 'detail1',    's': 25, 'e': 45},
        {'id': 'detail2',    's': 45, 'e': 65},
        {'id': 'comparison', 's': 65, 'e': 80},
        {'id': 'verdict',    's': 80, 'e': 95},
        {'id': 'cta',        's': 95, 'e': 110},
    ],
    'B': [
        {'id': 'hook',       's': 0,  'e': 6},
        {'id': 'overview',   's': 6,  'e': 20},
        {'id': 'detail1',    's': 20, 'e': 40},
        {'id': 'detail2',    's': 40, 'e': 60},
        {'id': 'comparison', 's': 60, 'e': 78},
        {'id': 'verdict',    's': 78, 'e': 92},
        {'id': 'cta',        's': 92, 'e': 110},
    ],
    'C': [
        {'id': 'hook',       's': 0,  'e': 10},
        {'id': 'overview',   's': 10, 'e': 28},
        {'id': 'detail1',    's': 28, 'e': 50},
        {'id': 'detail2',    's': 50, 'e': 68},
        {'id': 'comparison', 's': 68, 'e': 82},
        {'id': 'verdict',    's': 82, 'e': 96},
        {'id': 'cta',        's': 96, 'e': 115},
    ],
}


def _load_composites(produk_id, category='home', count=7):
    """Generate FRESH composite images every run.
    Deletes old cached composites to prevent duplicate content detection."""
    import glob

    # CLEANUP: delete old cached composites
    prod_dir = os.path.join(COMPOSITES_DIR, produk_id)
    if os.path.isdir(prod_dir):
        old = glob.glob(os.path.join(prod_dir, '*.png')) + glob.glob(os.path.join(prod_dir, '*.jpg'))
        for f in old:
            try: os.remove(f)
            except Exception: pass
    flat_old = glob.glob(os.path.join(COMPOSITES_DIR, f"{produk_id}_composite_*.png"))
    for f in flat_old:
        try: os.remove(f)
        except Exception: pass

    # ALWAYS generate fresh composites
    composites = _generate_fallback_composites(produk_id, category, count)

    # Ensure enough composites
    while len(composites) < count:
        idx = len(composites) % max(1, len(composites))
        composites.append(composites[idx].copy())

    # TRUE random shuffle (different order every run)
    random.shuffle(composites)

    return composites


def _generate_fallback_composites(produk_id, category, count=7):
    """Product image FILLS entire frame (cover mode) — sesuai acuan video."""
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
        variant_offset = random.randint(0, 100)
        for i in range(count):
            bg = create_premium_background(W, H, category=category, variant=i + variant_offset)
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


def _make_gradient_canvas(accent, index):
    """Last-resort gradient canvas (only if photo BG completely unavailable)."""
    grad = np.zeros((H, W, 3), dtype=np.uint8)
    hue_shift = index * 12
    top_color = tuple(min(255, max(0, c + hue_shift - 20)) for c in accent)
    bot_color = (15, 10, 20)
    for y in range(H):
        r = y / H
        for c in range(3):
            grad[y, :, c] = int(top_color[c] * (1 - r) + bot_color[c] * r)
    return Image.fromarray(grad)


def _ken_burns(composite_arr, t, duration, direction='zoom_in'):
    """Apply Ken Burns effect (zoom + pan) to a composite image."""
    h, w = composite_arr.shape[:2]
    progress = min(1.0, max(0.0, t / max(duration, 0.01)))

    directions = {
        'zoom_in':   (1.0, 1.15, 0.5, 0.5, 0.48, 0.45),
        'zoom_out':  (1.15, 1.0, 0.48, 0.45, 0.5, 0.5),
        'pan_left':  (1.10, 1.10, 0.55, 0.48, 0.45, 0.48),
        'pan_right': (1.10, 1.10, 0.45, 0.48, 0.55, 0.48),
        'pan_up':    (1.10, 1.10, 0.5, 0.55, 0.5, 0.42),
        'pan_down':  (1.10, 1.10, 0.5, 0.42, 0.5, 0.55),
    }
    ss, es, scx, scy, ecx, ecy = directions.get(direction, directions['zoom_in'])

    ease_p = 0.5 * (1 - math.cos(progress * math.pi))
    scale = ss + (es - ss) * ease_p
    cx = scx + (ecx - scx) * ease_p
    cy = scy + (ecy - scy) * ease_p

    crop_w = max(1, int(w / scale))
    crop_h = max(1, int(h / scale))
    x1 = max(0, min(int(cx * w - crop_w / 2), w - crop_w))
    y1 = max(0, min(int(cy * h - crop_h / 2), h - crop_h))

    cropped = composite_arr[y1:y1 + crop_h, x1:x1 + crop_w]
    return np.array(Image.fromarray(cropped).resize((W, H), Image.BILINEAR))


def _get_composite_frame(composites, t, cycle=15, dissolve_dur=0.5):
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


def _zoom_punch_transition(img1_arr, img2_arr, t, duration=0.5):
    """Zoom punch transition between two composite images."""
    progress = min(1.0, t / duration)
    if progress < 0.5:
        p = progress * 2
        frame = _ken_burns(img1_arr, p * 0.3, 1.0, 'zoom_in')
        fade = max(0, int((1.0 - p) * 255))
        return np.clip(frame * (fade / 255.0), 0, 255).astype(np.uint8)
    else:
        p = (progress - 0.5) * 2
        frame = _ken_burns(img2_arr, ease_out_cubic(p) * 0.2, 1.0, 'zoom_out')
        fade = min(255, int(p * 255))
        return np.clip(frame * (fade / 255.0), 0, 255).astype(np.uint8)


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


def generate_long(queue_file, output_dir):
    """Generate YouTube Long-form using PRE-COMPOSITED images with Ken Burns animation."""
    print(f"Generating YouTube Long from {queue_file}...")

    if not os.path.exists(queue_file):
        print(f"Queue not found: {queue_file}")
        return

    init_sounds()
    os.makedirs(os.path.join(output_dir, "yt"), exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")

    jobs = []
    with open(queue_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                jobs.append(json.loads(line.strip()))

    long_jobs = [j for j in jobs if j.get('video_type', 'long') == 'long']
    if not long_jobs:
        long_jobs = jobs

    # NOTE: QC mode no longer limits videos — ALL accounts must render
    # Previously: limited to 2 videos in QC mode, causing missing v1_yt

    font_path = _load_font(bold=False)
    font_bold = _load_font(bold=True)
    dur_cfg = VIDEO_DURATION.get('yt_long', {'min': 90, 'max': 120})
    target_dur = random.randint(dur_cfg['min'], dur_cfg['max'])

    for job in long_jobs:
        produk_id = job['produk_id']
        acct_id = job.get('account_id', 'yt_1')
        acct_num = int(acct_id.split('_')[1]) if '_' in acct_id else 1
        category = get_category(acct_id)
        channel = get_channel_name(acct_id)
        accent = get_accent_color(category)

        print(f"\nRendering YT Long for {produk_id} ({acct_id}, {category})...")

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
        sold_count = random.randint(1000, 15000)

        # === DYNAMIC FLOW STAGES (YT Long 90-120s) ===
        # Stage 1: Nama + teaser slide in from LEFT
        # Stage 2: Nama exits LEFT, gambar product slides in from RIGHT
        # Stage 3: Gambar goyang kiri-kanan, nama+harga muncul di atas
        # Stage 4: Gambar exits RIGHT, fitur/review text slides in
        # Stage 5: Fitur exits, CTA penutup slides in
        
        total_dur = target_dur
        S1_END = 10.0    # Nama + teaser
        S2_END = 14.0    # Transition: nama out, gambar in
        S3_END = 55.0    # Gambar goyang + info
        S4_END = 60.0    # Gambar out
        S5_END = 80.0    # Fitur/review text
        S6_END = 85.0    # Transition fitur out
        # S7 = 85 - total_dur: CTA
        
        SLIDE_DUR = 1.2  # Duration of slide animations
        PROD_SLIDE = 2.0  # Slower product entry

        try:
            # === LOAD COMPOSITE IMAGES (for backgrounds) ===
            composites = _load_composites(produk_id, category, count=7)
            print(f"  [OK] Loaded {len(composites)} composites")

            # Load product image separately for sway animation
            prod_img_pil = None
            for ext in ['png', 'jpg', 'webp']:
                p = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', f"{produk_id}.{ext}")
                if os.path.exists(p):
                    prod_img_pil = Image.open(p)
                    break
            
            # Scale product image for display
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
            
            # Frame border color (softer version of accent)
            border_color = tuple(min(255, c + 60) for c in accent)

            # Pure visual — NO text overlay, product image speaks for itself
            # All info (nama, harga, link) goes in description + pinned comment

            def make_frame(t):
                frame = _get_composite_frame(composites, t, cycle=15)
                frame = draw_frame_border(frame, accent_color=border_color, t=t)
                return frame

            # === ASSEMBLE VIDEO ===
            video = VideoClip(make_frame, duration=total_dur).with_fps(24)

            # === AUDIO (normalized) ===
            audio_clips = []
            # Get per-gender volume levels
            vo_vol, music_vol = get_voice_volumes(acct_id)

            music_dir = os.path.join(output_dir, "yt")
            music_path, music_tier = find_music_file(music_dir, produk_id, acct_id, category)
            if music_path:
                music = prepare_music(AudioFileClip(music_path), total_dur, music_vol=music_vol)
                audio_clips.append(music)

            # SFX at stage transitions
            stage_transitions = [S1_END, S2_END, S4_END, S6_END]

            # Ding at rating stars (stage 5, 14s in)
            ding_time = S4_END + 14.0

            # Bass drop at CTA
            cta_start = S6_END + 0.5

            if audio_clips:
                try:
                    video = video.with_audio(CompositeAudioClip(audio_clips))
                except Exception as e:
                    print(f"  [WARN] Audio failed: {e}")

            # === VOICEOVER: per-stage TTS ===
            vo_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers', produk_id, 'yt_long')
            vo_stages = [
                ('hook', 0.0), ('product', S1_END), ('feature', S4_END), ('cta', S6_END)
            ]
            vo_found = False
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
                        vo_found = True
                    except Exception:
                        pass
            if vo_found:
                try:
                    video = video.with_audio(CompositeAudioClip(audio_clips))
                except Exception:
                    pass

            # === EXPORT LONG ===
            out_file = f"{today}_{produk_id}_v{acct_num}_yt_long.mp4"
            out_path = os.path.join(output_dir, "yt", out_file)
            audio_params = get_ffmpeg_audio_params()
            video.write_videofile(out_path, fps=15, codec='libx264',
                                preset='ultrafast', logger=None,
                                **audio_params)
            print(f"  [OK] Long: {out_file} ({total_dur}s)")

            # === AUTO-EXTRACT SHORTS ===
            try:
                # Extract: Stage 1 (nama intro) + Stage 3 middle (product sway) + Stage 7 (CTA)
                hook_end = min(S1_END, total_dur)
                prod_mid_s = min(S2_END + 5, total_dur - 1)
                prod_mid_e = min(prod_mid_s + 15, S3_END, total_dur)
                cta_s = min(S6_END, total_dur - 1)
                cta_e = min(cta_s + 15, total_dur)

                if prod_mid_s >= total_dur or cta_s >= total_dur:
                    print(f"  [WARN] Shorts: video too short ({total_dur}s), skipping")
                else:
                    hook_clip = video.subclipped(0, hook_end)
                    prod_clip = video.subclipped(prod_mid_s, prod_mid_e)
                    cta_clip = video.subclipped(cta_s, cta_e)

                    shorts_video = concatenate_videoclips([hook_clip, prod_clip, cta_clip])
                    short_out = f"{today}_{produk_id}_v{acct_num}_yt.mp4"
                    short_path = os.path.join(output_dir, "yt", short_out)

                    if not os.path.exists(short_path):
                        shorts_video.write_videofile(short_path, fps=24, codec='libx264',
                                                   audio_codec='aac', preset='ultrafast',
                                                   logger=None)
                        print(f"  [OK] Short extracted: {short_out}")
                    shorts_video.close()
            except Exception as e:
                print(f"  [WARN] Shorts extraction failed: {e}")

            video.close()

        except Exception as e:
            import traceback
            print(f"  [FAIL] Long render: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    generate_long("engine/queue/yt_queue.jsonl", "engine/output")
