"""
generate_video_fb.py
Facebook: 50-60s product review — relaxed pace, more text info.

Architecture (per instruksi_upgrade_system.md Bagian 5):
  Uses PRE-COMPOSITED images animated with Ken Burns.
  Pace santai, lebih banyak info di teks, social proof diperpanjang.

Scenes:
  Hook(0-5s) -> Product(5-15s) -> Features(15-30s) -> Proof(30-45s) -> CTA(45-60s)
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
    text_slide_up, ease_out_cubic,
    create_rating_stars, create_chat_bubble, create_blinking_label,
    create_count_up_text, create_simple_price,
    draw_frame_border, slide_element_x, sway_x,
    render_outline_text, create_plain_gradient
)
from engine.modules.sound_manager import get_sfx_path, init_sounds
from engine.modules.audio_normalizer import prepare_music, prepare_sfx, get_ffmpeg_audio_params, find_music_file, get_voice_volumes

W, H = 1080, 1920
COMPOSITES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'composites')


def _load_composites(produk_id, category='home', count=5):
    """Generate FRESH composite images every run."""
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

    composites = _generate_fallback(produk_id, category, count)

    while len(composites) < count:
        composites.append(composites[len(composites) % max(1, len(composites))].copy())

    random.shuffle(composites)

    return composites


def _generate_fallback(produk_id, category, count=5):
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
            bg = create_premium_background(W, H, category=category, variant=i + variant_offset, platform='facebook')
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


def _make_gradient_fb(accent, index):
    """Last-resort gradient for FB."""
    grad = np.zeros((H, W, 3), dtype=np.uint8)
    top = tuple(min(255, max(0, c + index * 10)) for c in accent)
    bot = (25, 20, 15)
    for y in range(H):
        r = y / H
        for c in range(3):
            grad[y, :, c] = int(top[c] * (1 - r) + bot[c] * r)
    return Image.fromarray(grad)


def _get_composite_frame(composites, t, cycle=12, dissolve_dur=0.6):
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


def _cross_dissolve(img1, img2, t, duration=0.6):
    """Gentle cross-dissolve transition for Facebook."""
    progress = min(1.0, t / duration)
    ease_p = progress * progress * (3 - 2 * progress)  # smoothstep
    blended = (img1.astype(float) * (1 - ease_p) + img2.astype(float) * ease_p)
    return np.clip(blended, 0, 255).astype(np.uint8)


def _load_font(bold=False):
    try:
        from font_helper import get_font, get_font_bold
        path = get_font_bold() if bold else get_font()
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    for c in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf"]:
        if os.path.exists(c):
            return c
    return None


def generate_video_fb(queue_file, output_dir):
    """Generate Facebook videos using composite images with gentle Ken Burns."""
    print(f"Generating Facebook videos from {queue_file}...")

    if not os.path.exists(queue_file):
        print(f"Queue not found: {queue_file}")
        return

    init_sounds()
    os.makedirs(os.path.join(output_dir, "fb"), exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")

    jobs = []
    with open(queue_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                jobs.append(json.loads(line.strip()))

    font_path = _load_font(bold=False)
    font_bold = _load_font(bold=True)
    dur_cfg = VIDEO_DURATION.get('facebook', {'min': 50, 'max': 60})
    target_dur = random.randint(dur_cfg['min'], dur_cfg['max'])

    for job in jobs:
        produk_id = job['produk_id']
        acct_id = job.get('account_id', 'fb_1')
        category = get_category(acct_id)
        accent = get_accent_color(category)

        print(f"\nRendering FB video for {produk_id} ({acct_id}, {category})...")

        hooks = get_copywriting(category, 'hooks')
        ctas = get_copywriting(category, 'cta')
        hook_text = job.get('hook', random.choice(hooks) if hooks else 'Solusi terbaik!')
        nama = job.get('nama', produk_id)
        from engine.modules.image_utils import clean_product_name
        nama = clean_product_name(nama)
        harga = job.get('harga', '')
        desc = job.get('deskripsi_singkat', '')
        cta_text = job.get('cta', random.choice(ctas) if ctas else 'Link di deskripsi!')
        rating_val = round(random.uniform(4.5, 4.9), 1)
        sold_count = random.randint(500, 9999)

        total_dur = target_dur
        
        # === DYNAMIC FLOW STAGES (FB 50-60s) ===
        S1_END = 7.0     # Nama + teaser slide in
        S2_END = 10.0    # Transition: nama out, gambar in
        S3_END = 30.0    # Gambar goyang + info
        S4_END = 33.0    # Gambar out
        S5_END = 48.0    # Fitur/review text
        S6_END = 51.0    # Transition fitur out
        # S7 = 51 - total_dur: CTA
        
        SLIDE_DUR = 1.0
        PROD_SLIDE = 1.8  # Slower product entry

        kb_dirs = ['zoom_in', 'pan_left', 'pan_right', 'zoom_out', 'pan_up']
        random.shuffle(kb_dirs)

        try:
            composites = _load_composites(produk_id, category, count=5)
            print(f"  [OK] Loaded {len(composites)} composites")

            # Load product image for sway animation
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
            # All info (nama, harga, link) goes in post caption

            def make_frame(t):
                frame = _get_composite_frame(composites, t, cycle=12)
                frame = draw_frame_border(frame, accent_color=border_color, t=t)
                return frame

            video = VideoClip(make_frame, duration=total_dur).with_fps(24)

            audio_clips = []
            vo_vol, music_vol = get_voice_volumes(acct_id)

            music_dir = os.path.join(output_dir, "fb")
            music_path, music_tier = find_music_file(music_dir, produk_id, acct_id, category)
            if music_path:
                music = prepare_music(AudioFileClip(music_path), total_dur, music_vol=music_vol)
                audio_clips.append(music)



            # Voiceover
            vo_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers', produk_id, 'fb')
            vo_stages = [('hook', 0.0), ('product', S1_END), ('feature', S4_END), ('cta', S6_END)]
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

            out_file = f"{today}_{produk_id}_fb.mp4"
            out_path = os.path.join(output_dir, "fb", out_file)
            audio_params = get_ffmpeg_audio_params()
            video.write_videofile(out_path, fps=15, codec='libx264',
                                preset='ultrafast', logger=None,
                                **audio_params)
            print(f"  [OK] Facebook: {out_file} ({total_dur}s)")
            video.close()

        except Exception as e:
            import traceback
            print(f"  [FAIL] FB render: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    generate_video_fb("engine/queue/fb_queue.jsonl", "engine/output")
