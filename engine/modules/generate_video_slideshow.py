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
    get_random_transitions, apply_transition, TRANSITION_NAMES
)
from slideshow_frame import (
    render_frame, apply_vignette, apply_ken_burns,
    fit_image_to_frame, get_random_pattern
)
from audio_normalizer import (
    prepare_music, get_ffmpeg_audio_params, find_music_file
)
from sound_manager import init_sounds

W, H = 1080, 1920
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
        'slide_duration': 6.5,
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

    # If we have fewer than needed, duplicate with variations
    while len(images) < count:
        src = images[len(images) % unique_count].copy()
        # NO mirror — flipping makes text unreadable (e.g. product info reversed)
        images.append(src)
        print(f"    [QC] Slot {len(images)}: duplicated from image {(len(images)-1) % unique_count + 1}")

    return images[:count]


def _calculate_timeline(config):
    """Calculate the timeline (start/end times for each slide and transition).

    Returns list of segments:
      [{'type': 'slide', 'image_idx': 0, 'start': 0.0, 'end': 5.5, 'kb_dir': 'zoom_in'},
       {'type': 'transition', 'from_idx': 0, 'to_idx': 1, 'start': 5.5, 'end': 6.5, 'name': 'cube_rotate'},
       {'type': 'slide', 'image_idx': 1, 'start': 6.5, 'end': 12.0, 'kb_dir': 'pan_left'},
       ...]
    """
    num_imgs = config['num_images']
    slide_dur = config['slide_duration']
    trans_dur = config['transition_duration']
    passes = config['passes']

    segments = []
    t = 0.0
    img_idx = 0
    total_slides = num_imgs * passes

    # Prepare transitions (different set per pass)
    all_transitions = []
    for p in range(passes):
        trans = get_random_transitions(count=num_imgs - 1)
        # Pad if needed
        while len(trans) < num_imgs - 1:
            trans.append(random.choice(TRANSITION_NAMES))
        all_transitions.extend(trans)
        # Between passes, add one extra transition
        if p < passes - 1:
            all_transitions.append(random.choice(TRANSITION_NAMES))

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

    print(f"  Rendering {platform} slideshow for {produk_id}...")

    # Load images
    images_pil = _load_product_images(produk_id, num_imgs)
    if not images_pil:
        print(f"    [SKIP] No images for {produk_id}")
        return False

    # Fit images to frame — get product bounds for inner frame
    fitted = []
    bounds_list = []  # product_bounds per image
    for img in images_pil:
        fitted_img, prod_bounds = fit_image_to_frame(img, W, H, bg_color=(15, 15, 20))
        fitted.append(np.array(fitted_img))
        bounds_list.append(prod_bounds)

    # NO vignette — it darkens edges and makes product look blurry
    # Product images are only 800x800 upscaled to 1460px, vignette makes it worse

    # Calculate timeline
    segments, total_dur = _calculate_timeline(config)
    print(f"    Timeline: {len(segments)} segments, {total_dur:.1f}s total")

    # Running lights: always CHASE (berjalan, bukan kedip)
    light_pattern = 'chase'
    print(f"    Frame: {category}, lights={light_pattern}")

    def make_frame(t):
        # Find which segment we're in
        frame = np.full((H, W, 3), 15, dtype=np.uint8)  # Dark fallback

        for seg in segments:
            if seg['start'] <= t < seg['end']:
                if seg['type'] == 'slide':
                    idx = seg['image_idx']
                    local_t = t - seg['start']
                    slide_dur = seg['end'] - seg['start']

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

        # After last segment — show last image
        if t >= segments[-1]['end']:
            idx = segments[-1].get('image_idx',
                                    segments[-1].get('to_idx', 0))
            frame = render_frame(fitted[idx], t, category=category,
                                  pattern=light_pattern,
                                  product_bounds=bounds_list[idx])

        # Fade in from black
        if t < FADE_IN_DUR:
            fade = t / FADE_IN_DUR
            frame = np.clip(frame * fade, 0, 255).astype(np.uint8)

        # Fade out to black
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
        print(f"    [QC] Resolution: {W}x{H}, FPS: 30, Codec: H.264 High")
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
