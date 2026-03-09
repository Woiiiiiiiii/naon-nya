"""
generate_video_yt.py
YouTube Shorts: Full-screen Ken Burns product image + floating text overlays.
- Product image fills ENTIRE screen (sharp, no blur)
- Camera slowly pans/zooms (Ken Burns effect)
- Text overlays float on top with semi-transparent backgrounds
- Per-account color palette for text boxes
- 24fps, 2000k, 1080x1920
"""
import json
import os
import sys
import datetime
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy import VideoClip, CompositeVideoClip, ImageClip, AudioFileClip, afx


# Per-account text box color palettes
ACCOUNT_PALETTES = {
    1: {
        'hook_bg': (255, 193, 7, 220),      # Amber
        'masalah_bg': (220, 53, 69, 200),    # Red
        'solusi_bg': (40, 167, 69, 200),     # Green
        'cta_bg': (0, 123, 255, 230),        # Blue
    },
    2: {
        'hook_bg': (233, 30, 99, 220),       # Pink
        'masalah_bg': (156, 39, 176, 200),   # Purple
        'solusi_bg': (0, 188, 212, 200),      # Cyan
        'cta_bg': (255, 152, 0, 230),        # Orange
    },
    3: {
        'hook_bg': (76, 175, 80, 220),       # Green
        'masalah_bg': (244, 67, 54, 200),    # Red
        'solusi_bg': (33, 150, 243, 200),     # Blue
        'cta_bg': (255, 235, 59, 230),       # Yellow
    },
    4: {
        'hook_bg': (103, 58, 183, 220),      # Deep Purple
        'masalah_bg': (255, 87, 34, 200),    # Deep Orange
        'solusi_bg': (0, 150, 136, 200),      # Teal
        'cta_bg': (233, 30, 99, 230),        # Pink
    },
    5: {
        'hook_bg': (0, 188, 212, 220),       # Cyan
        'masalah_bg': (121, 85, 72, 200),    # Brown
        'solusi_bg': (139, 195, 74, 200),     # Light Green
        'cta_bg': (63, 81, 181, 230),        # Indigo
    }
}


def make_text_with_bg(text, font_path, font_size, text_color, bg_color, max_width, padding=20):
    """Create text image with rounded background box and word-wrap."""
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()

    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = font.getbbox(test_line)
        if bbox[2] > max_width - (padding * 2):
            if current_line:
                lines.append(current_line)
            current_line = word
        else:
            current_line = test_line
    if current_line:
        lines.append(current_line)
    if not lines:
        lines = [text]

    line_heights = []
    line_widths = []
    for line in lines:
        bbox = font.getbbox(line)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    line_spacing = 10
    total_text_height = sum(line_heights) + (len(lines) - 1) * line_spacing
    max_line_width = max(line_widths) if line_widths else 100

    img_w = min(max_line_width + padding * 2, max_width)
    img_h = total_text_height + padding * 2

    img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([(0, 0), (img_w - 1, img_h - 1)], radius=15, fill=bg_color)

    y = padding
    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        lw = bbox[2] - bbox[0]
        x = (img_w - lw) // 2
        draw.text((x, y), line, font=font, fill=text_color)
        y += line_heights[min(i, len(line_heights)-1)] + line_spacing

    return np.array(img)


def generate_video(queue_file, output_dir):
    print(f"Generating YouTube Shorts from {queue_file}...")

    if not os.path.exists(queue_file):
        print(f"Error: {queue_file} not found.")
        return

    os.makedirs(os.path.join(output_dir, "yt"), exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")

    jobs = []
    with open(queue_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                jobs.append(json.loads(line))

    from font_helper import get_font, get_font_bold
    font_path = get_font() or "arial.ttf"
    font_bold = get_font_bold() or font_path

    for job in jobs:
        produk_id = job['produk_id']
        acct_id = job.get('account_id', 'yt_1')
        acct_num = int(acct_id.split('_')[1]) if '_' in acct_id else 1
        variant_id = job.get('variant_id', acct_num)

        print(f"Rendering YT video for {produk_id} (Account {acct_id})...")

        width, height = 1080, 1920

        palette = ACCOUNT_PALETTES.get(acct_num, ACCOUNT_PALETTES[1])
        micro = job.get('micro_edits', {})
        text_y_off = micro.get('text_y_offset', 0)
        font_off = micro.get('font_size_offset', 0)

        timings = job.get('scene_timings', {
            'hook': {'start': 0, 'duration': 3},
            'masalah': {'start': 3, 'duration': 4},
            'solusi': {'start': 7, 'duration': 4},
            'cta': {'start': 11, 'duration': 4}
        })
        total_dur = max(t['start'] + t['duration'] for t in timings.values())

        try:
            # â”€â”€ BACKGROUND: Ken Burns full-screen product image â”€â”€
            img_path = f"engine/data/images/{produk_id}.jpg"
            if os.path.exists(img_path):
                try:
                    from image_effects import prepare_kenburns_image, make_kenburns_frame, get_preset
                    canvas = prepare_kenburns_image(img_path, variant_id - 1, width, height)
                    preset = get_preset(variant_id - 1)
                    
                    def kb_frame(t):
                        return make_kenburns_frame(canvas, t, total_dur, preset, width, height)
                    
                    bg = VideoClip(kb_frame, duration=total_dur).with_fps(24)
                except Exception as e:
                    print(f"  [WARN] Ken Burns failed: {e}, using static image")
                    bg = ImageClip(img_path).resized((width, height)).with_duration(total_dur)
            else:
                # No image â€” use dark background
                bg = VideoClip(lambda t: np.full((height, width, 3), 20, dtype=np.uint8),
                               duration=total_dur).with_fps(24)
            
            clips = [bg]
            txt_max_w = width - 80

            # â”€â”€ TEXT OVERLAYS (floating on top of full-screen image) â”€â”€
            # Position text in lower 60% to not block product image
            
            h_t = timings.get('hook', {'start': 0, 'duration': 3})
            hook_arr = make_text_with_bg(
                job['hook'], font_bold, 58 + font_off,
                (255, 255, 255), palette['hook_bg'], txt_max_w, 25
            )
            hook_clip = (ImageClip(hook_arr)
                .with_duration(h_t['duration'])
                .with_position(('center', 1200 + text_y_off))
                .with_start(h_t['start']))
            clips.append(hook_clip)

            m_t = timings.get('masalah', {'start': 3, 'duration': 4})
            masalah_arr = make_text_with_bg(
                job['masalah'], font_path, 46 + font_off,
                (255, 255, 255), palette['masalah_bg'], txt_max_w, 20
            )
            masalah_clip = (ImageClip(masalah_arr)
                .with_duration(m_t['duration'])
                .with_position(('center', 1300 + text_y_off))
                .with_start(m_t['start']))
            clips.append(masalah_clip)

            s_t = timings.get('solusi', {'start': 7, 'duration': 4})
            solusi_arr = make_text_with_bg(
                job['solusi'], font_path, 50 + font_off,
                (255, 255, 255), palette['solusi_bg'], txt_max_w, 20
            )
            solusi_clip = (ImageClip(solusi_arr)
                .with_duration(s_t['duration'])
                .with_position(('center', 1350 + text_y_off))
                .with_start(s_t['start']))
            clips.append(solusi_clip)

            c_t = timings.get('cta', {'start': 11, 'duration': 4})
            cta_arr = make_text_with_bg(
                job['cta'], font_bold, 54 + font_off,
                (255, 255, 255), palette['cta_bg'], txt_max_w, 25
            )
            cta_clip = (ImageClip(cta_arr)
                .with_duration(c_t['duration'])
                .with_position(('center', 1400 + text_y_off))
                .with_start(c_t['start']))
            clips.append(cta_clip)

            video = CompositeVideoClip(clips)

            # â”€â”€ AUDIO â”€â”€
            per_video_music = os.path.join(output_dir, "yt", f"MUSIC_{produk_id}_{acct_id}.mp3")
            per_video_wav = per_video_music.replace('.mp3', '.wav')
            bg_music_path = "engine/assets/background_music.mp3"
            music_path = None
            if os.path.exists(per_video_music):
                music_path = per_video_music
            elif os.path.exists(per_video_wav):
                music_path = per_video_wav
            elif os.path.exists(bg_music_path):
                music_path = bg_music_path

            if music_path:
                audio_bg = AudioFileClip(music_path)
                final_audio = audio_bg.with_effects([afx.AudioLoop(duration=total_dur)])
                video = video.with_audio(final_audio)

            output_path = os.path.join(output_dir, "yt",
                f"{today}_{produk_id}_v{variant_id}_yt.mp4")
            metadata_str = (f"product:{produk_id};account:{acct_id};"
                          f"variant:{variant_id};platform:youtube")

            video.write_videofile(
                output_path, fps=24, codec="libx264",
                audio_codec="aac", bitrate="2000k",
                ffmpeg_params=["-metadata", f"comment={metadata_str}"],
                logger=None
            )
            video.close()
            print(f"  [OK] {output_path}")

        except Exception as e:
            print(f"  [FAIL] Error rendering {acct_id}/{produk_id}: {e}")
            import traceback
            traceback.print_exc()
            return


if __name__ == "__main__":
    generate_video(
        "engine/queue/yt_queue.jsonl",
        "engine/output"
    )
