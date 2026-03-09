"""
generate_video_tt.py
TikTok: 25-30s FAST-PACED product review.

Architecture (per instruksi_upgrade_system.md Bagian 5):
  Uses PRE-COMPOSITED images animated with Ken Burns + fast transitions.
  Pace paling cepat, transisi agresif, teks besar dan bold.

Scenes:
  Hook(0-2s) -> Product(2-10s) -> Features(10-20s) -> CTA(20-30s)
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
    text_slide_up, ease_out_cubic, ease_out_back,
    create_rating_stars, create_blinking_label, create_count_up_text
)
from engine.modules.sound_manager import get_sfx_path, init_sounds

W, H = 1080, 1920
COMPOSITES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'composites')

# TikTok neon theme
TT_ACCENT = (255, 0, 100)
TT_GRAD_TOP = (35, 0, 50)
TT_GRAD_BOT = (15, 0, 25)


def _load_composites(produk_id, category='home', count=4):
    """Load pre-made composite images."""
    composites = []
    prod_dir = os.path.join(COMPOSITES_DIR, produk_id)

    if os.path.isdir(prod_dir):
        files = sorted([f for f in os.listdir(prod_dir)
                       if f.endswith(('.png', '.jpg')) and 'composite' in f.lower()])
        for f in files[:count]:
            img = Image.open(os.path.join(prod_dir, f)).convert('RGB')
            img = img.resize((W, H), Image.LANCZOS)
            composites.append(np.array(img))

    if not composites:
        for i in range(count):
            p = os.path.join(COMPOSITES_DIR, f"{produk_id}_composite_{i:03d}.png")
            if os.path.exists(p):
                img = Image.open(p).convert('RGB')
                img = img.resize((W, H), Image.LANCZOS)
                composites.append(np.array(img))

    if not composites:
        composites = _generate_fallback(produk_id, category, count)

    while len(composites) < count:
        composites.append(composites[len(composites) % max(1, len(composites))].copy())

    # Platform-specific shuffle so TT uses DIFFERENT composite order than YT/FB
    import random as _rng
    _rng.seed(f"tt_{produk_id}")
    _rng.shuffle(composites)

    return composites


def _generate_fallback(produk_id, category, count=4):
    """Generate composites: full-frame transparent product over background photo."""
    accent = get_accent_color(category)
    composites = []

    from engine.modules.image_compositor import get_random_background

    img_path = None
    for ext in ['jpg', 'png', 'webp']:
        p = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', f"{produk_id}.{ext}")
        if os.path.exists(p):
            img_path = p
            break

    product_rgba = None
    is_placeholder = False
    if img_path:
        # Check if this is a placeholder image (skip rembg — it would make it transparent)
        marker = img_path + '.placeholder'
        import os as _os
        is_placeholder = _os.path.exists(marker)
        
        if is_placeholder:
            # Placeholder: use as-is, no background removal
            try:
                product_rgba = Image.open(img_path).convert('RGBA')
            except Exception:
                pass
        else:
            # Real product image: remove background
            try:
                from engine.modules.image_compositor import remove_background
                product_rgba = remove_background(img_path)
            except Exception:
                try:
                    product_rgba = Image.open(img_path).convert('RGBA')
                except Exception:
                    pass
    if product_rgba is None:
        product_rgba = Image.new('RGBA', (400, 400), (*TT_ACCENT, 255))

    # Different positions per variation so product MOVES
    positions = [(0.50, 0.50), (0.42, 0.45), (0.58, 0.45), (0.50, 0.55)]

    pw, ph = product_rgba.size
    # Scale product to fill entire frame
    scale = max(W / pw, H / ph)
    new_w = int(pw * scale)
    new_h = int(ph * scale)
    product_big = product_rgba.resize((new_w, new_h), Image.LANCZOS)

    for i in range(count):
        bg_path = get_random_background(category)
        if bg_path and os.path.exists(bg_path):
            try:
                canvas = Image.open(bg_path).convert('RGBA').resize((W, H), Image.LANCZOS)
            except Exception:
                canvas = _make_gradient(i).convert('RGBA')
        else:
            canvas = _make_gradient(i).convert('RGBA')

        # Shift product position per variation
        px, py = positions[i % len(positions)]
        max_shift_x = max(0, new_w - W)
        max_shift_y = max(0, new_h - H)
        offset_x = int(max_shift_x * (1.0 - px))
        offset_y = int(max_shift_y * (1.0 - py))
        offset_x = max(0, min(offset_x, max_shift_x))
        offset_y = max(0, min(offset_y, max_shift_y))

        product_cropped = product_big.crop((offset_x, offset_y, offset_x + W, offset_y + H))
        canvas.paste(product_cropped, (0, 0), product_cropped)
        composites.append(np.array(canvas.convert('RGB')))

    return composites


def _make_gradient(index):
    """Last-resort TikTok neon gradient."""
    grad = np.zeros((H, W, 3), dtype=np.uint8)
    top = tuple(min(255, c + index * 20) for c in TT_GRAD_TOP)
    for y in range(H):
        r = y / H
        for c in range(3):
            grad[y, :, c] = int(top[c] * (1 - r) + TT_GRAD_BOT[c] * r)
    return Image.fromarray(grad)


def _ken_burns(composite_arr, t, duration, direction='zoom_in'):
    """Ken Burns effect for TikTok — more aggressive pacing."""
    h, w = composite_arr.shape[:2]
    progress = min(1.0, max(0.0, t / max(duration, 0.01)))

    dirs = {
        'zoom_in':   (1.0, 1.20, 0.5, 0.5, 0.48, 0.44),
        'zoom_out':  (1.20, 1.0, 0.48, 0.44, 0.5, 0.5),
        'pan_left':  (1.12, 1.12, 0.58, 0.48, 0.42, 0.48),
        'pan_right': (1.12, 1.12, 0.42, 0.48, 0.58, 0.48),
    }
    ss, es, scx, scy, ecx, ecy = dirs.get(direction, dirs['zoom_in'])
    ease_p = 0.5 * (1 - math.cos(progress * math.pi))

    scale = ss + (es - ss) * ease_p
    cx = scx + (ecx - scx) * ease_p
    cy = scy + (ecy - scy) * ease_p

    crop_w = max(1, int(w / scale))
    crop_h = max(1, int(h / scale))
    x1 = max(0, min(int(cx * w - crop_w / 2), w - crop_w))
    y1 = max(0, min(int(cy * h - crop_h / 2), h - crop_h))

    cropped = composite_arr[y1:y1 + crop_h, x1:x1 + crop_w]
    return np.array(Image.fromarray(cropped).resize((W, H), Image.LANCZOS))


def _flash_cut(img1, img2, t, duration=0.25):
    """Fast flash cut transition — TikTok style."""
    progress = min(1.0, t / duration)
    if progress < 0.3:
        return img1
    elif progress < 0.5:
        # White flash
        return np.full_like(img1, 255)
    else:
        return img2


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


def generate_video_tt(queue_file, output_dir):
    """Generate TikTok videos using composite images with aggressive Ken Burns."""
    print(f"Generating TikTok videos from {queue_file}...")

    if not os.path.exists(queue_file):
        print(f"Queue not found: {queue_file}")
        return

    init_sounds()
    os.makedirs(os.path.join(output_dir, "tt"), exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")

    jobs = []
    with open(queue_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                jobs.append(json.loads(line.strip()))

    font_path = _load_font(bold=False)
    font_bold = _load_font(bold=True)
    dur_cfg = VIDEO_DURATION.get('tiktok', {'min': 25, 'max': 30})
    target_dur = random.randint(dur_cfg['min'], dur_cfg['max'])

    for job in jobs:
        produk_id = job['produk_id']
        acct_id = job.get('account_id', 'tt_1')
        category = get_category(acct_id)
        accent = get_accent_color(category)

        print(f"\nRendering TikTok for {produk_id} ({acct_id}, {category})...")

        hooks = get_copywriting(category, 'hooks')
        ctas = get_copywriting(category, 'cta')
        hook_text = job.get('hook', random.choice(hooks) if hooks else 'WAJIB PUNYA!')
        nama = job.get('nama', produk_id)
        harga = job.get('harga', '')
        desc = job.get('deskripsi_singkat', '')
        cta_text = job.get('cta', random.choice(ctas) if ctas else 'Link di bio!')
        rating_val = round(random.uniform(4.5, 4.9), 1)
        sold_count = random.randint(500, 9999)

        total_dur = target_dur
        scenes = [
            {'id': 'hook',    's': 0,  'e': 2},
            {'id': 'product', 's': 2,  'e': 10},
            {'id': 'feature', 's': 10, 'e': 20},
            {'id': 'cta',     's': 20, 'e': total_dur},
        ]

        kb_dirs = ['zoom_in', 'pan_left', 'pan_right', 'zoom_out']
        random.shuffle(kb_dirs)
        TRANS_DUR = 0.25

        try:
            composites = _load_composites(produk_id, category, count=4)
            print(f"  [OK] Loaded {len(composites)} composites")

            scene_map = {
                'hook': composites[0], 'product': composites[1],
                'feature': composites[2], 'cta': composites[3],
            }

            txt_w = W - 80
            hook_img = render_text_image(hook_text, font_bold or font_path,
                                        64, (255, 255, 255), (*TT_ACCENT, 240), txt_w, 28)
            product_img = render_text_image(f"{nama}\n{harga}", font_bold or font_path,
                                           52, (255, 255, 255), (0, 0, 0, 220), txt_w, 24)
            feat_text = f"> {desc[:60]}" if desc else "> Fitur terbaik"
            feat_img = render_text_image(feat_text, font_path or "arial.ttf",
                                        44, (255, 255, 255), (40, 167, 69, 230), txt_w, 20)
            cta_img = render_text_image(f" {cta_text}", font_bold or font_path,
                                       56, (255, 255, 255), (220, 53, 69, 245), txt_w, 28)

            # Pre-compute element heights for dynamic positioning
            _stars_ref = create_rating_stars(rating_val, font_path or "arial.ttf", 40)
            cached_stars_h = _stars_ref.height

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

                composite = scene_map[scene_id]

                if scene_t < TRANS_DUR and prev_scene and prev_scene in scene_map:
                    frame = _flash_cut(scene_map[prev_scene], composite, scene_t, TRANS_DUR)
                else:
                    frame = _ken_burns(composite, scene_t, scene_dur, kb_dir)

                # Text overlays
                if scene_id == 'hook' and scene_t > 0.2:
                    ty = text_slide_up(hook_img, H, 1380, scene_t - 0.2, 0.25)
                    frame = paste_overlay_on_frame(frame, hook_img,
                                                  ((W - hook_img.width) // 2, ty))

                elif scene_id == 'product' and scene_t > 0.3:
                    ty = text_slide_up(product_img, H, 1370, scene_t - 0.3, 0.3)
                    frame = paste_overlay_on_frame(frame, product_img,
                                                  ((W - product_img.width) // 2, ty))

                elif scene_id == 'feature':
                    # Dynamic stack: feat → stars → terjual
                    base_y = 1280
                    if scene_t > 0.3:
                        ty = text_slide_up(feat_img, H, base_y, scene_t - 0.3, 0.3)
                        frame = paste_overlay_on_frame(frame, feat_img,
                                                      ((W - feat_img.width) // 2, ty))
                    if scene_t > 4.0:
                        stars = create_rating_stars(rating_val, font_path or "arial.ttf",
                                                  40, animated_t=scene_t - 4.0, total_dur=1.0)
                        stars_y = base_y + feat_img.height + 12
                        frame = paste_overlay_on_frame(frame, stars,
                                                      ((W - stars.width) // 2, stars_y))
                    if scene_t > 7.0:
                        cnt_t = scene_t - 7.0
                        current = int(min(cnt_t / 2.0, 1.0) * sold_count)
                        cnt_img = create_count_up_text(current, "Terjual",
                                                      font_path or "arial.ttf", accent)
                        cnt_y = base_y + feat_img.height + 12 + cached_stars_h + 10
                        frame = paste_overlay_on_frame(frame, cnt_img,
                                                      ((W - cnt_img.width) // 2, cnt_y))

                elif scene_id == 'cta':
                    # Dynamic stack: CTA → STOK TERBATAS
                    if scene_t > 0.3:
                        ty = text_slide_up(cta_img, H, 1200, scene_t - 0.3, 0.3)
                        frame = paste_overlay_on_frame(frame, cta_img,
                                                      ((W - cta_img.width) // 2, ty))
                    if scene_t > 2.0:
                        stok_y = 1200 + cta_img.height + 15
                        blink = create_blinking_label(" STOK TERBATAS!",
                                                     font_bold or font_path or "arial.ttf",
                                                     TT_ACCENT, scene_t, 0.5)
                        frame = paste_overlay_on_frame(frame, blink,
                                                      ((W - blink.width) // 2, stok_y))

                return frame

            video = VideoClip(make_frame, duration=total_dur).with_fps(24)

            # Audio
            audio_clips = []
            music_file = os.path.join(output_dir, "tt", f"MUSIC_{produk_id}_{acct_id}.mp3")
            if os.path.exists(music_file):
                music = AudioFileClip(music_file)
                if music.duration < total_dur:
                    music = concatenate_audioclips([music] * (int(total_dur / music.duration) + 1))
                music = music.subclipped(0, total_dur).with_effects([afx.MultiplyVolume(0.70)])
                audio_clips.append(music)

            for sfx_name, sfx_time in [('swoosh', 0.2), ('pop', 2.0), ('swoosh', 10.0), ('bass_drop', 20.0)]:
                sfx_path = get_sfx_path(sfx_name)
                if sfx_path and os.path.exists(sfx_path) and sfx_time < total_dur:
                    try:
                        sfx = AudioFileClip(sfx_path).with_effects([afx.MultiplyVolume(0.55)])
                        audio_clips.append(sfx.with_start(sfx_time))
                    except Exception:
                        pass

            if audio_clips:
                try:
                    video = video.with_audio(CompositeAudioClip(audio_clips))
                except Exception as e:
                    print(f"  [WARN] Audio failed: {e}")

            out_file = f"{today}_{produk_id}_tt.mp4"
            out_path = os.path.join(output_dir, "tt", out_file)
            video.write_videofile(out_path, fps=15, codec='libx264',
                                audio_codec='aac', preset='ultrafast', logger=None)
            print(f"  [OK] TikTok: {out_file} ({total_dur}s)")
            video.close()

        except Exception as e:
            import traceback
            print(f"  [FAIL] TikTok render: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    generate_video_tt("engine/queue/tt_queue.jsonl", "engine/output")
