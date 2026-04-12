"""
generate_video_slideshow.py
Unified video generator for ALL platforms (YT, TT, FB).

Architecture:
  - Load 3-4 product images (original Shopee seller images)
  - Display each full-screen with decorative frame + running lights
  - Creative transitions between images (cube, roll, split, push, zoom)
  - Background music only (NO text overlay, NO voiceover, NO branding)
  - Fade in/out from black

Platform configs:
  - TikTok:   4 images, ~28s
  - YT Short: 3 images, ~26s
  - Facebook:  4 images, ~35s
  - YT Long:  4+4 images (2 passes, different transitions), ~63s
"""
import json
import os
import sys
import random
import datetime
import math
import numpy as np
from PIL import Image
from moviepy import (VideoClip, AudioFileClip, CompositeAudioClip,
                     afx, concatenate_audioclips)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from category_router import (
    get_category, get_accent_color, VIDEO_DURATION
)
from slideshow_transitions import (
    get_channel_transitions, apply_transition, TRANSITION_NAMES
)
from slideshow_frame import (
    render_frame, apply_vignette, apply_ken_burns,
    fit_image_to_frame, get_random_pattern
)
from audio_normalizer import (
    prepare_music, get_ffmpeg_audio_params, find_music_file
)
from sound_manager import init_sounds

# Default: portrait (Shorts, TikTok, FB)
W, H = 1080, 1920

# Per-platform resolution:
# YouTube Long = landscape 16:9 (agar TIDAK masuk Shorts)
# Semua lainnya = portrait 9:16
PLATFORM_RESOLUTION = {
    'tt':       (1080, 1920),  # Portrait 9:16
    'yt_short': (1080, 1920),  # Portrait 9:16 (Shorts)
    'fb':       (1080, 1920),  # Portrait 9:16
    'yt_long':  (1920, 1080),  # Landscape 16:9 (Long-form)
}
IMAGES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'images')

# Ken Burns directions to cycle through
KB_DIRECTIONS = ['zoom_in', 'pan_left', 'zoom_out', 'pan_right']

# ═══════════════════════════════════════════════════════════════════
#  Platform configs
# ═══════════════════════════════════════════════════════════════════
PLATFORM_CONFIG = {
    'tt': {
        'num_images': 4,
        'slide_duration': 5.5,
        'transition_duration': 1.0,
        'passes': 1,
        'output_subdir': 'tt',
        'suffix': '_tt',
    },
    'yt_short': {
        'num_images': 3,
        'slide_duration': 7.0,
        'transition_duration': 1.0,
        'passes': 1,
        'output_subdir': 'yt',
        'suffix': '_yt',
    },
    'fb': {
        'num_images': 4,
        'slide_duration': 7.0,
        'transition_duration': 1.0,
        'passes': 1,
        'output_subdir': 'fb',
        'suffix': '_fb',
    },
    'yt_long': {
        'num_images': 4,
        'slide_duration': 7.5,
        'transition_duration': 1.0,
        'passes': 2,  # 2 full passes with different transitions
        'output_subdir': 'yt',
        'suffix': '_yt_long',
    },
}

# Fade durations
FADE_IN_DUR = 0.5
FADE_OUT_DUR = 1.5


def _qc_image(img, label=""):
    """Quality check a single image. Returns (pass, reason)."""
    w, h = img.size
    # Minimum size check
    if w < 200 or h < 200:
        return False, f"too small ({w}x{h})"
    # Check if image is mostly one color (broken/placeholder)
    arr = np.array(img)
    std = arr.std()
    if std < 5.0:
        return False, f"solid color (std={std:.1f})"
    return True, f"{w}x{h} ok"


def _images_are_different(img1, img2, threshold=0.95):
    """Check if two images are different enough (not duplicates).
    Returns True if images are sufficiently different."""
    # Resize both to small thumbnails for fast comparison
    s1 = img1.resize((64, 64), Image.BILINEAR)
    s2 = img2.resize((64, 64), Image.BILINEAR)
    a1 = np.array(s1).astype(float)
    a2 = np.array(s2).astype(float)
    # Normalized correlation
    diff = np.abs(a1 - a2).mean() / 255.0
    return diff > (1.0 - threshold)  # diff > 0.05 = different enough


def _load_product_images(produk_id, count=4):
    """Load product images for slideshow.

    Image ordering (follows Shopee seller convention):
      _1.jpg = Cover utama produk (main product photo)
      _2.jpg = Manfaat/fungsi  (benefits/features)
      _3.jpg = Cara pemakaian  (how to use)
      _4.jpg = Keunggulan      (advantages/specs)

    Shopee sellers typically upload images in this order.
    We save them as _1, _2, _3, _4 preserving the seller's order.

    QC checks:
      - Minimum size: 200x200
      - Not solid color (corrupt/placeholder)
      - Not duplicate of another image
    """
    images = []
    qc_log = []

    # Try numbered images first (from multi-image download)
    for i in range(1, count + 1):
        for ext in ['jpg', 'png', 'webp']:
            p = os.path.join(IMAGES_DIR, f"{produk_id}_{i}.{ext}")
            if os.path.exists(p):
                try:
                    img = Image.open(p).convert('RGB')
                    passed, reason = _qc_image(img, f"_{i}")
                    if passed:
                        # Check if duplicate of existing image
                        is_dup = False
                        for existing in images:
                            if not _images_are_different(img, existing):
                                is_dup = True
                                break
                        if is_dup:
                            qc_log.append(f"    [QC] _{i}: DUPLICATE — skipped")
                        else:
                            images.append(img)
                            qc_log.append(f"    [QC] _{i}: {reason}")
                    else:
                        qc_log.append(f"    [QC] _{i}: FAIL — {reason}")
                    break
                except Exception as e:
                    qc_log.append(f"    [QC] _{i}: ERROR — {e}")

    # Fallback: try single image
    if not images:
        for ext in ['jpg', 'png', 'webp']:
            p = os.path.join(IMAGES_DIR, f"{produk_id}.{ext}")
            if os.path.exists(p):
                try:
                    img = Image.open(p).convert('RGB')
                    passed, reason = _qc_image(img, "main")
                    if passed:
                        images.append(img)
                        qc_log.append(f"    [QC] main: {reason}")
                    else:
                        qc_log.append(f"    [QC] main: FAIL — {reason}")
                    break
                except Exception:
                    pass

    # Print QC log
    for line in qc_log:
        print(line)

    if not images:
        print(f"    [QC-FAIL] No valid images for {produk_id}")
        return []

    unique_count = len(images)
    print(f"    [QC] {unique_count} unique images loaded (need {count})")

    # If we have fewer than needed, duplicate with VISUAL VARIATIONS
    # Each copy looks different: zoom, brightness, contrast, warmth
    # This makes single-image products interesting (not monotonous)
    variation_styles = [
        {'zoom': 1.15, 'bright': 1.05, 'contrast': 1.0, 'warmth': 0},
        {'zoom': 1.0, 'bright': 0.95, 'contrast': 1.10, 'warmth': 10},
        {'zoom': 1.10, 'bright': 1.0, 'contrast': 1.05, 'warmth': -8},
        {'zoom': 1.20, 'bright': 1.08, 'contrast': 0.95, 'warmth': 5},
        {'zoom': 1.05, 'bright': 0.98, 'contrast': 1.08, 'warmth': -5},
        {'zoom': 1.12, 'bright': 1.03, 'contrast': 1.0, 'warmth': 8},
        {'zoom': 1.08, 'bright': 1.0, 'contrast': 1.12, 'warmth': -3},
    ]
    var_idx = 0
    while len(images) < count:
        src = images[len(images) % unique_count].copy()
        # Apply visual variation
        style = variation_styles[var_idx % len(variation_styles)]
        var_idx += 1
        w, h = src.size

        # Zoom: crop center then resize back
        z = style['zoom']
        if z > 1.0:
            cw, ch = int(w / z), int(h / z)
            x1, y1 = (w - cw) // 2, (h - ch) // 2
            src = src.crop((x1, y1, x1 + cw, y1 + ch)).resize((w, h), Image.LANCZOS)

        # Brightness
        if style['bright'] != 1.0:
            from PIL import ImageEnhance
            src = ImageEnhance.Brightness(src).enhance(style['bright'])

        # Contrast
        if style['contrast'] != 1.0:
            from PIL import ImageEnhance
            src = ImageEnhance.Contrast(src).enhance(style['contrast'])

        # Warmth shift (add/subtract from red channel)
        if style['warmth'] != 0:
            arr = np.array(src)
            arr[:,:,0] = np.clip(arr[:,:,0].astype(int) + style['warmth'], 0, 255).astype(np.uint8)
            src = Image.fromarray(arr)

        images.append(src)
        print(f"    [QC] Slot {len(images)}: variation {var_idx} (zoom={z:.2f}, bright={style['bright']}, contrast={style['contrast']})")

    return images[:count]


def _calculate_timeline(config, platform='tt'):
    """Calculate the timeline (start/end times for each slide and transition).

    Each platform gets its own unique transition order (no duplicates).

    Returns list of segments:
      [{'type': 'slide', 'image_idx': 0, 'start': 0.0, 'end': 5.5, 'kb_dir': 'zoom_in'},
       {'type': 'transition', 'from_idx': 0, 'to_idx': 1, 'start': 5.5, 'end': 6.5, 'name': 'fade_dissolve'},
       {'type': 'slide', 'image_idx': 1, 'start': 6.5, 'end': 12.0, 'kb_dir': 'pan_left'},
       ...]
    """
    num_imgs = config['num_images']
    slide_dur = config['slide_duration']
    trans_dur = config['transition_duration']
    passes = config['passes']

    total_slides = num_imgs * passes
    total_transitions = total_slides - 1

    # Get per-channel transition sequence (unique order, no duplicates)
    all_transitions = get_channel_transitions(platform, total_transitions)
    print(f"    Transitions ({platform}): {' → '.join(all_transitions[:total_transitions])}")

    segments = []
    t = 0.0
    trans_idx = 0
    for slide_num in range(total_slides):
        # Slide segment
        img_i = slide_num % num_imgs
        kb_dir = KB_DIRECTIONS[slide_num % len(KB_DIRECTIONS)]
        segments.append({
            'type': 'slide',
            'image_idx': img_i,
            'start': t,
            'end': t + slide_dur,
            'kb_dir': kb_dir,
        })
        t += slide_dur

        # Transition segment (not after last slide)
        if slide_num < total_slides - 1 and trans_idx < len(all_transitions):
            next_img_i = (slide_num + 1) % num_imgs
            segments.append({
                'type': 'transition',
                'from_idx': img_i,
                'to_idx': next_img_i,
                'start': t,
                'end': t + trans_dur,
                'name': all_transitions[trans_idx],
            })
            t += trans_dur
            trans_idx += 1

    return segments, t  # segments, total_duration


def _render_slideshow(produk_id, category, config, output_path, music_dir,
                      acct_id=None):
    """Render a slideshow video for a specific platform config."""
    platform = config['suffix'].strip('_')
    num_imgs = config['num_images']

    # Get platform-specific resolution
    vid_w, vid_h = PLATFORM_RESOLUTION.get(platform, (W, H))
    print(f"  Rendering {platform} slideshow for {produk_id} ({vid_w}x{vid_h})...")

    # Load images
    images_pil = _load_product_images(produk_id, num_imgs)
    if not images_pil:
        print(f"    [SKIP] No images for {produk_id}")
        return False

    # Count truly unique images (before duplication fills slots)
    unique_count = len(set(id(img) for img in images_pil))
    # If all are same object copies, treat as 1 unique
    if unique_count <= 1 or len(images_pil) == 1:
        unique_count = 1

    # Fit images to frame — get product bounds for inner frame
    fitted = []
    bounds_list = []  # product_bounds per image
    for img in images_pil:
        fitted_img, prod_bounds = fit_image_to_frame(img, vid_w, vid_h, bg_color=(15, 15, 20))
        fitted.append(np.array(fitted_img))
        bounds_list.append(prod_bounds)

    # NO vignette — it darkens edges and makes product look blurry
    # Product images are only 800x800 upscaled to 1460px, vignette makes it worse

    # Calculate timeline — same structure for ALL products
    # Single-image products use visual variations, so transitions still look good
    segments, content_dur = _calculate_timeline(config, platform=platform)

    # Fades are EXTRA TIME — they don't eat into slide durations
    # Offset all segments forward by FADE_IN_DUR
    for seg in segments:
        seg['start'] += FADE_IN_DUR
        seg['end'] += FADE_IN_DUR

    # Total video = fade_in + content + fade_out
    total_dur = FADE_IN_DUR + content_dur + FADE_OUT_DUR
    print(f"    Timeline: {len(segments)} segments, {content_dur:.1f}s content + {FADE_IN_DUR}s fade_in + {FADE_OUT_DUR}s fade_out = {total_dur:.1f}s total")

    # Running lights: always CHASE (berjalan, bukan kedip)
    light_pattern = 'chase'
    print(f"    Frame: {category}, lights={light_pattern}")

    def make_frame(t):
        # Find which segment we're in
        frame = np.full((vid_h, vid_w, 3), 15, dtype=np.uint8)  # Dark fallback

        for seg in segments:
            if seg['start'] <= t < seg['end']:
                if seg['type'] == 'slide':
                    idx = seg['image_idx']

                    # Product image is STATIC (no Ken Burns movement)
                    frame = fitted[idx].copy()

                    # Frame + running lights (pass product bounds)
                    frame = render_frame(frame, t, category=category,
                                          pattern=light_pattern,
                                          product_bounds=bounds_list[idx])

                elif seg['type'] == 'transition':
                    from_idx = seg['from_idx']
                    to_idx = seg['to_idx']
                    local_t = t - seg['start']
                    trans_dur = seg['end'] - seg['start']
                    progress = local_t / max(trans_dur, 0.01)

                    # Apply frame to both source images
                    img1 = render_frame(fitted[from_idx], t, category=category,
                                         pattern=light_pattern,
                                         product_bounds=bounds_list[from_idx])
                    img2 = render_frame(fitted[to_idx], t, category=category,
                                         pattern=light_pattern,
                                         product_bounds=bounds_list[to_idx])

                    frame = apply_transition(img1, img2, progress, seg['name'])

                break

        # Before first segment — show first image (during fade-in time)
        if t < segments[0]['start']:
            frame = fitted[0].copy()
            frame = render_frame(frame, t, category=category,
                                  pattern=light_pattern,
                                  product_bounds=bounds_list[0])

        # After last segment — show last image (during fade-out time)
        if t >= segments[-1]['end']:
            idx = segments[-1].get('image_idx',
                                    segments[-1].get('to_idx', 0))
            frame = render_frame(fitted[idx], t, category=category,
                                  pattern=light_pattern,
                                  product_bounds=bounds_list[idx])

        # Fade in from black (EXTRA TIME before content)
        if t < FADE_IN_DUR:
            fade = t / FADE_IN_DUR
            frame = np.clip(frame * fade, 0, 255).astype(np.uint8)

        # Fade out to black (EXTRA TIME after content)
        if t > total_dur - FADE_OUT_DUR:
            fade = max(0, (total_dur - t) / FADE_OUT_DUR)
            frame = np.clip(frame * fade, 0, 255).astype(np.uint8)

        return frame

    # Build video
    video = VideoClip(make_frame, duration=total_dur).with_fps(30)

    # Audio
    audio_clips = []

    # Find music
    # Slideshow has NO voiceover — music is the ONLY audio track.
    # Use LOUDER normalization (bypass the quiet background level).
    _acct = acct_id or 'yt_1'
    music_path, music_tier = find_music_file(music_dir, produk_id, _acct, category)
    if music_path:
        try:
            raw_music = AudioFileClip(music_path)
            # Loop if needed
            if raw_music.duration < total_dur:
                reps = int(total_dur / raw_music.duration) + 1
                raw_music = concatenate_audioclips([raw_music] * reps)
            raw_music = raw_music.subclipped(0, total_dur)
            # Boost volume — raw music files are often quiet
            raw_music = raw_music.with_effects([afx.MultiplyVolume(2.5)])
            audio_clips.append(raw_music)
        except Exception as e:
            print(f"    [WARN] Music failed: {e}")

    if audio_clips:
        try:
            video = video.with_audio(CompositeAudioClip(audio_clips))
        except Exception as e:
            print(f"    [WARN] Audio composite failed: {e}")

    # Export
    audio_params = get_ffmpeg_audio_params()
    video.write_videofile(
        output_path, fps=30, codec='libx264',
        preset='slow', logger=None,  # 'slow' = better quality encoding
        ffmpeg_params=['-profile:v', 'high', '-level', '4.1',
                       '-b:v', '5M', '-maxrate', '6M', '-bufsize', '8M'],
        **audio_params
    )
    video.close()

    # ═══ POST-RENDER QC ═══
    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        size_mb = file_size / (1024 * 1024)
        if file_size < 100_000:  # < 100KB = corrupt
            print(f"    [QC-FAIL] Output too small ({size_mb:.1f}MB) — likely corrupt")
            os.remove(output_path)
            return False
        print(f"    [OK] {os.path.basename(output_path)} ({total_dur:.0f}s, {size_mb:.1f}MB)")
        print(f"    [QC] Resolution: {vid_w}x{vid_h}, FPS: 30, Codec: H.264 High")
        return True
    else:
        print(f"    [QC-FAIL] Output file not created!")
        return False


# ═══════════════════════════════════════════════════════════════════
#  Main entry points
# ═══════════════════════════════════════════════════════════════════
def generate_slideshow_all(output_dir):
    """Generate slideshow videos for ALL platforms from ALL queue files."""
    init_sounds()
    today = datetime.datetime.now().strftime("%Y%m%d")

    queue_map = {
        'yt': ('engine/queue/yt_queue.jsonl', ['yt_long', 'yt_short']),
        'tt': ('engine/queue/tt_queue.jsonl', ['tt']),
        'fb': ('engine/queue/fb_queue.jsonl', ['fb']),
    }

    for platform_key, (queue_file, platforms) in queue_map.items():
        if not os.path.exists(queue_file):
            print(f"  [SKIP] Queue not found: {queue_file}")
            continue

        jobs = []
        with open(queue_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    jobs.append(json.loads(line.strip()))

        if not jobs:
            print(f"  [SKIP] No jobs in {queue_file}")
            continue

        for job in jobs:
            produk_id = job['produk_id']
            acct_id = job.get('account_id', f'{platform_key}_1')
            category = get_category(acct_id)

            for plat in platforms:
                config = PLATFORM_CONFIG[plat]
                os.makedirs(os.path.join(output_dir, config['output_subdir']),
                            exist_ok=True)

                # Build output filename
                acct_num = ''
                if '_' in acct_id:
                    try:
                        acct_num = f"_v{acct_id.split('_')[1]}"
                    except Exception:
                        pass

                out_file = f"{today}_{produk_id}{acct_num}{config['suffix']}.mp4"
                out_path = os.path.join(output_dir, config['output_subdir'],
                                         out_file)

                # Skip if already exists
                if os.path.exists(out_path):
                    print(f"  [SKIP] Already exists: {out_file}")
                    continue

                music_dir = os.path.join(output_dir, config['output_subdir'])

                try:
                    _render_slideshow(
                        produk_id, category, config, out_path, music_dir,
                        acct_id=acct_id
                    )
                except Exception as e:
                    import traceback
                    print(f"  [FAIL] {plat} render for {produk_id}: {e}")
                    traceback.print_exc()


if __name__ == "__main__":
    generate_slideshow_all("engine/output")
