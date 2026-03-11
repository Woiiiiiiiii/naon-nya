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
    get_channel_name, VIDEO_DURATION
)
from engine.modules.video_effects import (
    render_text_image, paste_overlay_on_frame,
    text_slide_up, ease_out_back, ease_out_cubic,
    create_rating_stars, create_price_display, create_chat_bubble,
    create_count_up_text, create_blinking_label, create_simple_price
)
from engine.modules.sound_manager import get_sfx_path, init_sounds
from engine.modules.audio_normalizer import prepare_music, prepare_sfx, get_ffmpeg_audio_params

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
    """Load pre-made composite images for this product."""
    composites = []

    # Check product-specific directory
    prod_dir = os.path.join(COMPOSITES_DIR, produk_id)
    if os.path.isdir(prod_dir):
        files = sorted([f for f in os.listdir(prod_dir)
                       if f.endswith(('.png', '.jpg')) and 'composite' in f.lower()])
        for f in files[:count]:
            img = Image.open(os.path.join(prod_dir, f)).convert('RGB')
            img = img.resize((W, H), Image.LANCZOS)
            composites.append(np.array(img))

    # Check flat naming
    if not composites:
        for i in range(count):
            p = os.path.join(COMPOSITES_DIR, f"{produk_id}_composite_{i:03d}.png")
            if os.path.exists(p):
                img = Image.open(p).convert('RGB')
                img = img.resize((W, H), Image.LANCZOS)
                composites.append(np.array(img))

    # Fallback: generate composites
    if not composites:
        composites = _generate_fallback_composites(produk_id, category, count)

    # Ensure enough composites
    while len(composites) < count:
        idx = len(composites) % max(1, len(composites))
        composites.append(composites[idx].copy())

    # Platform-specific shuffle so YT Long uses DIFFERENT composite order than TT/FB
    import random as _rng
    _rng.seed(f"yt_long_{produk_id}")
    _rng.shuffle(composites)

    return composites


def _generate_fallback_composites(produk_id, category, count=7):
    """Product on PREMIUM gradient background (glow + vignette + shadow)."""
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

    pw, ph = product_img.size
    scale = min(W / pw, H / ph) * 0.75
    new_w, new_h = int(pw * scale), int(ph * scale)
    img_scaled = product_img.resize((new_w, new_h), Image.LANCZOS)

    vy_shifts = [0.0, -0.02, 0.02, -0.03, 0.03, -0.01, 0.01]
    for i in range(count):
        vy = vy_shifts[i % len(vy_shifts)]
        canvas = create_premium_background(W, H, category=category, variant=i)
        paste_x = (W - new_w) // 2
        paste_y = (H - new_h) // 2 + int(H * vy)
        paste_y = max(0, min(paste_y, H - new_h))
        add_product_shadow(canvas, img_scaled, paste_x, paste_y)
        if is_transparent:
            canvas.paste(img_scaled, (paste_x, paste_y), img_scaled.split()[3])
        else:
            canvas.paste(img_scaled, (paste_x, paste_y))
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
        harga = job.get('harga', '')
        desc = job.get('deskripsi_singkat', '')
        cta_text = job.get('cta', random.choice(ctas) if ctas else 'Link di deskripsi!')
        rating_val = round(random.uniform(4.5, 4.9), 1)
        sold_count = random.randint(1000, 15000)

        # Select scene template
        template_key = random.choice(list(TEMPLATES.keys()))
        scenes = [s.copy() for s in TEMPLATES[template_key]]
        total_dur = min(target_dur, scenes[-1]['e'])

        # Ken Burns direction bank
        kb_dirs = ['zoom_in', 'pan_left', 'zoom_out', 'pan_right', 'pan_up', 'pan_down', 'zoom_in']
        random.shuffle(kb_dirs)

        TRANS_DUR = 0.5

        try:
            # === LOAD 7 COMPOSITE IMAGES ===
            composites = _load_composites(produk_id, category, count=7)
            print(f"  [OK] Loaded {len(composites)} composites")

            scene_composites = {}
            for i, sc in enumerate(scenes):
                scene_composites[sc['id']] = composites[i % len(composites)]

            # Pre-render text overlays
            txt_w = W - 100
            hook_img = render_text_image(hook_text, font_bold or font_path,
                                        56, (255, 255, 255), (*accent, 235), txt_w, 24)
            overview_text = f"{nama}\n{harga}" if harga else nama
            overview_img = render_text_image(overview_text, font_bold or font_path,
                                           48, (255, 255, 255), (0, 0, 0, 210), txt_w, 22)
            feat_text = f"{desc[:80]}" if desc else "Fitur unggulan produk ini"
            feat_img = render_text_image(feat_text, font_path or "arial.ttf",
                                        42, (255, 255, 255), (40, 167, 69, 220), txt_w, 18)
            detail2_text = "Kualitas bahan premium, tahan lama"
            detail2_img = render_text_image(detail2_text, font_path or "arial.ttf",
                                           40, (255, 255, 255), (0, 123, 255, 210), txt_w, 18)
            comparison_text = "Lebih baik dari kompetitor sejenis"
            comparison_img = render_text_image(comparison_text, font_path or "arial.ttf",
                                              42, (255, 255, 255), (108, 117, 125, 220), txt_w, 18)
            verdict_text = f"Rating: {rating_val}/5 | Sangat Recommended!"
            verdict_img = render_text_image(verdict_text, font_bold or font_path,
                                           44, (255, 255, 255), (40, 167, 69, 230), txt_w, 22)
            cta_img = render_text_image(f" {cta_text}", font_bold or font_path,
                                       50, (255, 255, 255), (220, 53, 69, 240), txt_w, 24)

            # Pre-compute element heights for dynamic positioning (avoid recreating per frame)
            _stars_ref = create_rating_stars(rating_val, font_path or "arial.ttf", 40)
            cached_stars_h = _stars_ref.height
            _bubble_ref = create_chat_bubble("Bagus banget, sesuai deskripsi! Recommended ",
                                             font_path or "arial.ttf", side='left', accent_color=accent)
            cached_bubble_h = _bubble_ref.height

            def make_frame(t):
                scene_id = 'hook'
                scene_t = t
                prev_scene = None
                for i, sc in enumerate(scenes):
                    if sc['s'] <= t < sc['e']:
                        scene_id = sc['id']
                        scene_t = t - sc['s']
                        if i > 0:
                            prev_scene = scenes[i - 1]['id']
                        break

                scene_idx = next(i for i, sc in enumerate(scenes) if sc['id'] == scene_id)
                scene_dur = scenes[scene_idx]['e'] - scenes[scene_idx]['s']
                kb_dir = kb_dirs[scene_idx % len(kb_dirs)]

                composite = scene_composites[scene_id]

                # Transition between scenes
                if scene_t < TRANS_DUR and prev_scene and prev_scene in scene_composites:
                    frame = _zoom_punch_transition(
                        scene_composites[prev_scene], composite, scene_t, TRANS_DUR)
                else:
                    frame = _ken_burns(composite, scene_t, scene_dur, kb_dir)

                # ═══════════════════════════════════════════
                # ZONE LAYOUT:
                #   TOP    Y=60-200:  Product name + price (persistent, blink)
                #   CENTER Y=250-1420: Product image (untouched)
                #   BOTTOM Y=1460+:   Scene-specific text
                # ═══════════════════════════════════════════

                # === TOP ZONE: Product name + price (PERSISTENT) ===
                title_label = create_blinking_label(
                    f" {nama} ", font_bold or font_path or "arial.ttf",
                    accent, t, 1.2, font_size=44
                )
                title_y = 130
                frame = paste_overlay_on_frame(frame, title_label,
                                               ((W - title_label.width) // 2, title_y))

                if harga:
                    price_label = create_simple_price(f"Rp {harga}", font_bold or font_path or "arial.ttf",
                                                      50, accent)
                    price_y = title_y + title_label.height + 10
                    frame = paste_overlay_on_frame(frame, price_label,
                                                   ((W - price_label.width) // 2, price_y))

                # === BOTTOM ZONE: Scene-specific text (Y=1460+) ===
                BOTTOM_Y = 1580

                if scene_id == 'hook' and scene_t > 0.3:
                    ty = text_slide_up(hook_img, H, BOTTOM_Y, scene_t - 0.3, 0.4)
                    frame = paste_overlay_on_frame(frame, hook_img,
                                                   ((W - hook_img.width) // 2, ty))

                elif scene_id == 'overview' and scene_t > 0.8:
                    ty = text_slide_up(overview_img, H, BOTTOM_Y, scene_t - 0.8, 0.4)
                    frame = paste_overlay_on_frame(frame, overview_img,
                                                   ((W - overview_img.width) // 2, ty))

                elif scene_id == 'detail1':
                    base_y = BOTTOM_Y
                    if scene_t > 0.5:
                        ty = text_slide_up(feat_img, H, base_y, scene_t - 0.5, 0.35)
                        frame = paste_overlay_on_frame(frame, feat_img,
                                                       ((W - feat_img.width) // 2, ty))
                    if scene_t > 5.0:
                        stars = create_rating_stars(rating_val, font_path or "arial.ttf",
                                                   40, animated_t=scene_t - 5.0, total_dur=1.5)
                        stars_y = base_y + feat_img.height + 12
                        frame = paste_overlay_on_frame(frame, stars,
                                                       ((W - stars.width) // 2, stars_y))
                    if scene_t > 10.0:
                        cnt_t = scene_t - 10.0
                        current = int(min(cnt_t / 2.5, 1.0) * sold_count)
                        cnt_img = create_count_up_text(current, "Terjual",
                                                       font_path or "arial.ttf", accent)
                        cnt_y = base_y + feat_img.height + 12
                        if scene_t > 5.0:
                            cnt_y += cached_stars_h + 10
                        frame = paste_overlay_on_frame(frame, cnt_img,
                                                       ((W - cnt_img.width) // 2, cnt_y))

                elif scene_id == 'detail2' and scene_t > 0.5:
                    ty = text_slide_up(detail2_img, H, BOTTOM_Y, scene_t - 0.5, 0.35)
                    frame = paste_overlay_on_frame(frame, detail2_img,
                                                   ((W - detail2_img.width) // 2, ty))

                elif scene_id == 'comparison' and scene_t > 0.8:
                    ty = text_slide_up(comparison_img, H, BOTTOM_Y, scene_t - 0.8, 0.4)
                    frame = paste_overlay_on_frame(frame, comparison_img,
                                                   ((W - comparison_img.width) // 2, ty))

                elif scene_id == 'verdict':
                    if scene_t > 0.5:
                        review_text = "Bagus banget, sesuai deskripsi! Recommended "
                        bubble = create_chat_bubble(review_text, font_path or "arial.ttf",
                                                    side='left', accent_color=accent)
                        slide_t = min((scene_t - 0.5) / 0.4, 1.0)
                        bx = int(-bubble.width + (80 + bubble.width) * ease_out_cubic(slide_t))
                        frame = paste_overlay_on_frame(frame, bubble, (bx, BOTTOM_Y))
                    if scene_t > 3.0:
                        verdict_y = BOTTOM_Y + cached_bubble_h + 15
                        ty = text_slide_up(verdict_img, H, verdict_y, scene_t - 3.0, 0.4)
                        frame = paste_overlay_on_frame(frame, verdict_img,
                                                       ((W - verdict_img.width) // 2, ty))

                elif scene_id == 'cta':
                    if scene_t > 0.5:
                        ty = text_slide_up(cta_img, H, BOTTOM_Y, scene_t - 0.5, 0.35)
                        frame = paste_overlay_on_frame(frame, cta_img,
                                                       ((W - cta_img.width) // 2, ty))
                    if scene_t > 3.0:
                        stok_y = BOTTOM_Y + cta_img.height + 15
                        blink = create_blinking_label(" STOK TERBATAS!",
                                                      font_bold or font_path or "arial.ttf",
                                                      (220, 53, 69), scene_t, 0.6)
                        frame = paste_overlay_on_frame(frame, blink,
                                                       ((W - blink.width) // 2, stok_y))

                return frame

            # === ASSEMBLE VIDEO ===
            video = VideoClip(make_frame, duration=total_dur).with_fps(24)

            # === AUDIO (normalized) ===
            audio_clips = []
            music_file = os.path.join(output_dir, "yt", f"MUSIC_{produk_id}_{acct_id}.mp3")
            if os.path.exists(music_file):
                music = prepare_music(AudioFileClip(music_file), total_dur)
                audio_clips.append(music)

            # SFX at scene transitions
            for sc in scenes:
                if sc['s'] > 0:
                    sfx_path = get_sfx_path('swoosh')
                    if sfx_path and os.path.exists(sfx_path) and sc['s'] < total_dur:
                        try:
                            sfx = prepare_sfx(AudioFileClip(sfx_path), sc['s'])
                            audio_clips.append(sfx)
                        except Exception:
                            pass

            # Ding at rating stars
            ding_time = scenes[2]['s'] + 5.0
            sfx_path = get_sfx_path('ding')
            if sfx_path and os.path.exists(sfx_path) and ding_time < total_dur:
                try:
                    sfx = prepare_sfx(AudioFileClip(sfx_path), ding_time)
                    audio_clips.append(sfx)
                except Exception:
                    pass

            # Bass drop at CTA
            cta_start = scenes[-1]['s'] + 0.5
            sfx_path = get_sfx_path('bass_drop')
            if sfx_path and os.path.exists(sfx_path) and cta_start < total_dur:
                try:
                    sfx = prepare_sfx(AudioFileClip(sfx_path), cta_start)
                    audio_clips.append(sfx)
                except Exception:
                    pass

            if audio_clips:
                try:
                    video = video.with_audio(CompositeAudioClip(audio_clips))
                except Exception as e:
                    print(f"  [WARN] Audio failed: {e}")

            # === VOICEOVER: per-scene TTS (clip to scene gap) ===
            vo_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers', produk_id, 'yt_long')
            vo_scenes_list = [(s['id'], s['s'] + 0.3) for s in scenes]
            vo_found = False
            for idx, (scene_id, start_time) in enumerate(vo_scenes_list):
                vo_path = os.path.join(vo_dir, f"vo_{scene_id}.mp3")
                if os.path.exists(vo_path) and start_time < total_dur:
                    try:
                        vo = AudioFileClip(vo_path)
                        # Clip VO so it doesn't overlap with next scene
                        if idx + 1 < len(vo_scenes_list):
                            max_dur = vo_scenes_list[idx + 1][1] - start_time - 0.3
                        else:
                            max_dur = total_dur - start_time - 0.2
                        if max_dur > 0.5 and vo.duration > max_dur:
                            vo = vo.subclipped(0, max_dur)
                        from engine.modules.audio_normalizer import normalize_audio_clip, VOICEOVER_VOLUME
                        vo = normalize_audio_clip(vo)
                        vo = vo.with_effects([afx.MultiplyVolume(VOICEOVER_VOLUME)])
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
                short_dur = random.randint(45, 50)
                hook_end = min(5, scenes[0]['e'])
                detail_s = scenes[2]['s']
                detail_e = min(detail_s + 15, scenes[2]['e'])
                verdict_s = scenes[5]['s']
                verdict_e = min(verdict_s + 15, scenes[5]['e'])

                hook_clip = video.subclipped(0, hook_end)
                detail_clip = video.subclipped(detail_s, detail_e)
                closing_clip = video.subclipped(verdict_s, min(verdict_e, total_dur))

                shorts_video = concatenate_videoclips([hook_clip, detail_clip, closing_clip])
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
