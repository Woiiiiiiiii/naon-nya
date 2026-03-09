"""
color_grading.py
Apply cinematic color grading per category using FFmpeg filters.
Each category has a distinct visual identity.
"""
import os
import subprocess
import json

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')

# FFmpeg color grading presets per category
COLOR_PRESETS = {
    'fashion': {
        'label': 'Warm & Vibrant',
        'filter': 'eq=brightness=0.04:saturation=1.3:contrast=1.05,colortemperature=t=5500',
    },
    'gadget': {
        'label': 'Cool & Premium Dark',
        'filter': 'eq=brightness=-0.02:saturation=0.95:contrast=1.1,colortemperature=t=7000',
    },
    'beauty': {
        'label': 'Soft Pastel',
        'filter': 'eq=brightness=0.06:saturation=0.9:contrast=0.95,colortemperature=t=5000',
    },
    'home': {
        'label': 'Clean & Bright',
        'filter': 'eq=brightness=0.05:saturation=1.1:contrast=1.0,colortemperature=t=5500',
    },
    'health': {
        'label': 'Energetic & Vivid',
        'filter': 'eq=brightness=0.03:saturation=1.25:contrast=1.08,colortemperature=t=6000',
    },
    'wellness': {
        'label': 'Energetic & Vivid',
        'filter': 'eq=brightness=0.03:saturation=1.25:contrast=1.08,colortemperature=t=6000',
    },
}

# Category name mapping
CATEGORY_MAP = {
    'Fashion': 'fashion',
    'Elektronik': 'gadget',
    'Kosmetik': 'beauty',
    'Alat Rumah Tangga': 'home',
    'Kesehatan dan Olahraga': 'wellness',
    'fashion': 'fashion',
    'gadget': 'gadget',
    'beauty': 'beauty',
    'home': 'home',
    'health': 'wellness',
    'wellness': 'wellness',
}


def get_grading_filter(category):
    """Get FFmpeg color grading filter for a category."""
    key = CATEGORY_MAP.get(category, 'home')
    preset = COLOR_PRESETS.get(key, COLOR_PRESETS['home'])
    return preset['filter']


def apply_color_grading(input_path, output_path, category):
    """Apply color grading to a video using FFmpeg."""
    grading = get_grading_filter(category)

    cmd = [
        'ffmpeg', '-y', '-i', input_path,
        '-vf', grading,
        '-c:v', 'libx264', '-crf', '20', '-preset', 'medium',
        '-c:a', 'copy',
        '-movflags', '+faststart',
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            # Replace original with graded version
            os.replace(output_path, input_path)
            print(f"  [OK] Color graded: {os.path.basename(input_path)} ({category})")
            return True
        else:
            print(f"  [WARN] Color grading failed: {result.stderr[:200]}")
            # Clean up failed output
            if os.path.exists(output_path):
                os.remove(output_path)
            return False
    except Exception as e:
        print(f"  [WARN] Color grading error: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False


def grade_all_videos(output_dir):
    """Apply color grading to all rendered videos."""
    print("=== Color Grading Engine ===")
    total, graded = 0, 0

    for platform in ['yt', 'tt', 'fb']:
        plat_dir = os.path.join(output_dir, platform)
        if not os.path.isdir(plat_dir):
            continue

        for fname in os.listdir(plat_dir):
            if not fname.endswith('.mp4') or fname.startswith('MUSIC_'):
                continue

            # Determine category from filename metadata or queue
            # For now, use account-based category detection
            video_path = os.path.join(plat_dir, fname)
            temp_path = video_path + '.grading.mp4'

            # Extract category from video metadata comment
            category = _detect_category_from_video(video_path)

            if category:
                if apply_color_grading(video_path, temp_path, category):
                    graded += 1
                total += 1

    print(f"=== Color grading complete: {graded}/{total} ===")


def _detect_category_from_video(video_path):
    """Try to detect category from video metadata comment."""
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json',
               '-show_format', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            info = json.loads(result.stdout)
            comment = info.get('format', {}).get('tags', {}).get('comment', '')
            # Parse metadata like "product:xxx;account:yt_1;platform:youtube"
            for part in comment.split(';'):
                if part.startswith('account:'):
                    acct = part.split(':')[1]
                    # Map account to category
                    from category_router import get_category
                    return get_category(acct)
    except Exception:
        pass
    return 'home'  # Default fallback


if __name__ == "__main__":
    output_dir = "engine/output"
    if os.path.isdir(output_dir):
        grade_all_videos(output_dir)
    else:
        print("=== Color Grading: No output dir found, skipping ===")
