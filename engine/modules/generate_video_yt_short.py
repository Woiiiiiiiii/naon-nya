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
    get_channel_name, VIDEO_DURATION
)
from engine.modules.video_effects import (
    render_text_image, paste_overlay_on_frame,
    text_slide_up, create_rating_stars,
    create_price_display, create_chat_bubble, create_blinking_label,
    create_count_up_text, ease_out_cubic, ease_out_back,
    create_simple_price
)
from engine.modules.sound_manager import get_sfx_path, init_sounds
from engine.modules.audio_normalizer import prepare_music, prepare_sfx, get_ffmpeg_audio_params

W, H = 1080, 1920
COMPOSITES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'composites')
DEPTH_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'depth_maps')


def _load_composites(produk_id, category='home', count=5):
    """Load pre-made composite images for this product.
    Falls back to generating simple composites if none found."""
    composites = []
    prod_dir = os.path.join(COMPOSITES_DIR, produk_id)

    if os.path.isdir(prod_dir):
        files = sorted([f for f in os.listdir(prod_dir)
                       if f.endswith(('.png', '.jpg')) and 'composite' in f.lower()])
        for f in files[:count]:
            img = Image.open(os.path.join(prod_dir, f)).convert('RGB')
            img = img.resize((W, H), Image.LANCZOS)
            composites.append(np.array(img))

    # Also check flat naming convention
    if not composites:
        for i in range(count):
            p = os.path.join(COMPOSITES_DIR, f"{produk_id}_composite_{i:03d}.png")
            if os.path.exists(p):
                img = Image.open(p).convert('RGB')
                img = img.resize((W, H), Image.LANCZOS)
                composites.append(np.array(img))

    # Fallback: generate simple composites from product image + gradient bg
    if not composites:
        composites = _generate_fallback_composites(produk_id, category, count)

    # Ensure we have at least 'count' composites (duplicate if needed)
    while len(composites) < count:
        composites.append(composites[len(composites) % max(1, len(composites))].copy())

    # Platform-specific shuffle so YT Short uses DIFFERENT composite order than Long/TT/FB
    import random as _rng
    _rng.seed(f"yt_short_{produk_id}")
    _rng.shuffle(composites)

    return composites


def _generate_fallback_composites(produk_id, category, count=5):
    """Product on PREMIUM gradient background (glow + vignette + shadow)."""
    from engine.modules.premium_background import create_premium_background, add_product_shadow

    composites = []

    img_path = None
    for ext in ['png', 'jpg', 'webp']:  # PNG first (transparent product from rembg)
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
    # CONTAIN mode: fit ENTIRE product in frame (never crop)
    scale = min(W / pw, H / ph) * 0.75  # 75% of frame (more room for glow)
    new_w, new_h = int(pw * scale), int(ph * scale)
    img_scaled = product_img.resize((new_w, new_h), Image.LANCZOS)

    vy_shifts = [0.0, -0.02, 0.02, -0.03, 0.03]
    for i in range(count):
        vy = vy_shifts[i % len(vy_shifts)]
        # Premium gradient background with glow + vignette
        canvas = create_premium_background(W, H, category=category, variant=i)
        paste_x = (W - new_w) // 2
        paste_y = (H - new_h) // 2 + int(H * vy)
        paste_y = max(0, min(paste_y, H - new_h))
        # Add shadow below product
        add_product_shadow(canvas, img_scaled, paste_x, paste_y)
        # Paste product (alpha-aware)
        if is_transparent:
            canvas.paste(img_scaled, (paste_x, paste_y), img_scaled.split()[3])
        else:
            canvas.paste(img_scaled, (paste_x, paste_y))
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
        harga = job.get('harga', '')
        desc = job.get('deskripsi_singkat', '')
        cta_text = job.get('cta', random.choice(ctas) if ctas else 'Link di deskripsi!')
        rating_val = round(random.uniform(4.5, 4.9), 1)
        sold_count = random.randint(500, 9999)

        total_dur = target_dur
        scenes = [
            {'id': 'hook',    's': 0,  'e': 3},
            {'id': 'hero',    's': 3,  'e': 12},
            {'id': 'feature', 's': 12, 'e': 30},
            {'id': 'proof',   's': 30, 'e': 40},
            {'id': 'cta',     's': 40, 'e': total_dur},
        ]

        # Ken Burns directions per scene
        kb_directions = ['zoom_in', 'pan_left', 'pan_right', 'zoom_out', 'pan_up']
        random.shuffle(kb_directions)

        try:
            # === LOAD COMPOSITE IMAGES ===
            composites = _load_composites(produk_id, category, count=5)
            print(f"  [OK] Loaded {len(composites)} composites")

            # Scene-to-composite mapping:
            # Each scene uses a different composite image
            scene_composites = {
                'hook': composites[0],
                'hero': composites[1],
                'feature': composites[2],
                'proof': composites[3],
                'cta': composites[4],
            }

            # Pre-render text overlays
            txt_w = W - 100

            hook_img = render_text_image(hook_text, font_bold or font_path,
                                        56, (255, 255, 255), (*accent, 235), txt_w, 24)
            hero_text = f"{nama}"
            if harga:
                hero_text += f"\nHarga: {harga}"
            hero_img = render_text_image(hero_text, font_bold or font_path,
                                        48, (255, 255, 255), (0, 0, 0, 210), txt_w, 22)

            feat_text = f"{desc[:80]}" if desc else "Fitur unggulan produk ini"
            feat_img = render_text_image(feat_text, font_path or "arial.ttf",
                                        42, (255, 255, 255), (40, 167, 69, 220), txt_w, 18)

            cta_img = render_text_image(f" {cta_text}", font_bold or font_path,
                                       50, (255, 255, 255), (220, 53, 69, 240), txt_w, 24)

            # Pre-compute element heights for dynamic positioning
            _stars_ref = create_rating_stars(rating_val, font_path or "arial.ttf", 40)
            cached_stars_h = _stars_ref.height
            _bubble_ref = create_chat_bubble("Bagus banget, sesuai deskripsi! Recommended ",
                                             font_path or "arial.ttf", side='left', accent_color=accent)
            cached_bubble_h = _bubble_ref.height

            # Transition timing (0.4s overlap between scenes)
            TRANS_DUR = 0.4

            def make_frame(t):
                # Determine current scene
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

                scene_dur = next((sc['e'] - sc['s'] for sc in scenes if sc['id'] == scene_id), 5)
                kb_dir = kb_directions[scenes.index(next(s for s in scenes if s['id'] == scene_id)) % len(kb_directions)]

                # === COMPOSITE IMAGE ANIMATION ===
                composite = scene_composites[scene_id]

                # Transition between scenes (zoom punch)
                if scene_t < TRANS_DUR and prev_scene and prev_scene in scene_composites:
                    prev_comp = scene_composites[prev_scene]
                    frame = _zoom_punch_transition(prev_comp, composite, scene_t, TRANS_DUR)
                else:
                    # Ken Burns on current composite
                    anim_t = scene_t if scene_t >= TRANS_DUR else 0
                    frame = _ken_burns(composite, anim_t, scene_dur, kb_dir)

                # ═══════════════════════════════════════════
                # ZONE LAYOUT (precise, no overlap):
                #   TOP    Y=60-200:  Product name + price (persistent, blink)
                #   CENTER Y=250-1420: Product image (untouched)
                #   BOTTOM Y=1460+:   Scene-specific text
                # ═══════════════════════════════════════════

                # === TOP ZONE: Product name + price (PERSISTENT, all scenes) ===
                title_label = create_blinking_label(
                    f" {nama} ", font_bold or font_path or "arial.ttf",
                    accent, t, 1.2, font_size=44
                )
                title_y = 130
                frame = paste_overlay_on_frame(frame, title_label,
                                               ((W - title_label.width) // 2, title_y))

                if harga:
                    price_label = create_simple_price(harga, font_bold or font_path or "arial.ttf",
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

                elif scene_id == 'hero' and scene_t > 0.8:
                    ty = text_slide_up(hero_img, H, BOTTOM_Y, scene_t - 0.8, 0.4)
                    frame = paste_overlay_on_frame(frame, hero_img,
                                                   ((W - hero_img.width) // 2, ty))

                elif scene_id == 'feature':
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
                    if scene_t > 8.0:
                        cnt_t = scene_t - 8.0
                        current = int(min(cnt_t / 2.0, 1.0) * sold_count)
                        cnt_img = create_count_up_text(current, "Terjual",
                                                       font_path or "arial.ttf", accent)
                        cnt_y = base_y + feat_img.height + 12
                        if scene_t > 5.0:
                            cnt_y += cached_stars_h + 10
                        frame = paste_overlay_on_frame(frame, cnt_img,
                                                       ((W - cnt_img.width) // 2, cnt_y))

                elif scene_id == 'proof':
                    bubble1_y = BOTTOM_Y
                    if scene_t > 0.5:
                        review_text = "Bagus banget, sesuai deskripsi! Recommended "
                        bubble = create_chat_bubble(review_text, font_path or "arial.ttf",
                                                    side='left', accent_color=accent)
                        slide_t = min((scene_t - 0.5) / 0.4, 1.0)
                        bx = int(-bubble.width + (80 + bubble.width) * ease_out_cubic(slide_t))
                        frame = paste_overlay_on_frame(frame, bubble, (bx, bubble1_y))

                    if scene_t > 3.0:
                        bubble2_y = bubble1_y + cached_bubble_h + 12
                        review2 = "Worth it sih, harga segini kualitas ok !"
                        bubble2 = create_chat_bubble(review2, font_path or "arial.ttf",
                                                     side='right', accent_color=(80, 80, 90))
                        slide_t2 = min((scene_t - 3.0) / 0.4, 1.0)
                        bx2 = int(W + 10 - (W + 10 - 300) * ease_out_cubic(slide_t2))
                        frame = paste_overlay_on_frame(frame, bubble2,
                                                       (min(bx2, W - bubble2.width - 20), bubble2_y))

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

            # === AUDIO: Music + SFX + Voiceover (normalized) ===
            audio_clips = []

            music_dir = os.path.join(output_dir, "yt")
            music_file = os.path.join(music_dir, f"MUSIC_{produk_id}_{acct_id}.mp3")
            if os.path.exists(music_file):
                music = prepare_music(AudioFileClip(music_file), total_dur)
                audio_clips.append(music)

            sfx_entries = [
                ('swoosh', 0.3),
                ('pop', 3.0),       # Transition hook->hero
                ('swoosh', 12.0),   # Transition hero->feature
                ('ding', 17.0),
                ('swoosh', 30.0),   # Transition feature->proof
                ('bass_drop', 40.0),# Transition proof->cta
            ]
            for sfx_name, sfx_time in sfx_entries:
                sfx_path = get_sfx_path(sfx_name)
                if sfx_path and os.path.exists(sfx_path) and sfx_time < total_dur:
                    try:
                        sfx = prepare_sfx(AudioFileClip(sfx_path), sfx_time)
                        audio_clips.append(sfx)
                    except Exception:
                        pass

            # === VOICEOVER: covers every scene (clip to scene gap) ===
            vo_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers', produk_id, 'yt_short')
            scene_starts_list = [('hook', 0.3), ('hero', 4.0), ('feature', 13.0), ('proof', 31.0), ('cta', 41.0)]
            for idx, (scene_id, start_time) in enumerate(scene_starts_list):
                vo_path = os.path.join(vo_dir, f"vo_{scene_id}.mp3")
                if os.path.exists(vo_path) and start_time < total_dur:
                    try:
                        vo = AudioFileClip(vo_path)
                        # Clip VO so it doesn't overlap with next scene
                        if idx + 1 < len(scene_starts_list):
                            max_dur = scene_starts_list[idx + 1][1] - start_time - 0.3
                        else:
                            max_dur = total_dur - start_time - 0.2
                        if max_dur > 0.5 and vo.duration > max_dur:
                            vo = vo.subclipped(0, max_dur)
                        from engine.modules.audio_normalizer import normalize_audio_clip, VOICEOVER_VOLUME
                        vo = normalize_audio_clip(vo)
                        vo = vo.with_effects([afx.MultiplyVolume(VOICEOVER_VOLUME)])
                        vo = vo.with_start(start_time)
                        audio_clips.append(vo)
                    except Exception:
                        pass

            if audio_clips:
                try:
                    final_audio = CompositeAudioClip(audio_clips)
                    video = video.with_audio(final_audio)
                except Exception as e:
                    print(f"  [WARN] Audio composite failed: {e}")

            # === EXPORT ===
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
