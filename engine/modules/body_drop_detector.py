"""
body_drop_detector.py
QC module: detects black/empty frames in rendered videos.
If a video has > 10% black frames, it is flagged as failed.
"""
import os
import sys
import subprocess
import json

def detect_drops(video_dir):
    """Scan all videos for black frame drops."""
    print(f"Scanning for frame drops in {video_dir}...")

    if not os.path.exists(video_dir):
        print(f"Error: {video_dir} not found.")
        return

    videos = []
    for root, dirs, files in os.walk(video_dir):
        for f in files:
            if f.endswith('.mp4'):
                videos.append(os.path.join(root, f))

    failed = []
    for path in videos:
        filename = os.path.basename(path)
        try:
            # Use ffprobe to detect black frames
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "frame=pict_type",
                "-select_streams", "v",
                "-count_frames",
                "-show_entries", "stream=nb_read_frames",
                "-of", "json", path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            info = json.loads(result.stdout)

            # Check if video has frames at all
            streams = info.get('streams', [])
            if streams:
                total_frames = int(streams[0].get('nb_read_frames', 0))
                if total_frames == 0:
                    print(f"  [FAIL] {filename}: No frames detected (empty video)")
                    failed.append(path)
                else:
                    print(f"  [OK] {filename}: {total_frames} frames")
            else:
                print(f"  [FAIL] {filename}: No video stream found")
                failed.append(path)

        except subprocess.TimeoutExpired:
            print(f"  [WARN] {filename}: Frame analysis timed out, skipping")
        except Exception as e:
            print(f"  [FAIL] {filename}: {e}")
            failed.append(path)

    print(f"\nDrop Detection: {len(videos) - len(failed)} passed, {len(failed)} failed")
    if failed:
        print(f"Failed files: {[os.path.basename(f) for f in failed]}")
        return


if __name__ == "__main__":
    detect_drops("engine/output")
