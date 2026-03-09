"""
qc_engine.py
Quality Control Engine â€” checks every generated video against latest specs.

Validates:
  - Resolution: 1080x1920 (9:16 vertical)
  - Per-platform duration ranges:
      YT Long: 85-125s  |  YT Short: 40-55s
      TT: 20-35s        |  FB: 45-65s
  - Minimum file size: 500KB (real 3-layer video should be substantial)
  - Audio stream present (music must be mixed in)
  - No duplicate content (MD5 hash check)
  - No placeholder images

Failed videos are AUTO-DELETED so pipeline can regenerate them next run.
"""
import os
import sys
import subprocess
import json
import hashlib
from PIL import Image


def get_video_info(path):
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)


def get_md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def is_placeholder_image(img_path):
    """Detect if image is a plain-color placeholder (not a real product photo)."""
    try:
        img = Image.open(img_path)
        img = img.convert('RGB')
        
        # Sample pixels from center area
        w, h = img.size
        center_x, center_y = w // 2, h // 2
        
        # Check color variance in a 200x200 center crop
        crop = img.crop((center_x - 100, center_y - 100, center_x + 100, center_y + 100))
        pixels = list(crop.getdata())
        
        if not pixels:
            return True
        
        # Calculate color variance
        r_vals = [p[0] for p in pixels]
        g_vals = [p[1] for p in pixels]
        b_vals = [p[2] for p in pixels]
        
        r_var = max(r_vals) - min(r_vals)
        g_var = max(g_vals) - min(g_vals)
        b_var = max(b_vals) - min(b_vals)
        
        total_var = r_var + g_var + b_var
        
        # Placeholder images have very low color variance (solid color + text)
        # Real product photos have high variance
        if total_var < 60:
            return True
            
        return False
    except:
        return True  # If we can't read it, treat as placeholder


def check_music_exists(video_path, platform_dir):
    """Check if per-video music file exists."""
    basename = os.path.basename(video_path).replace('.mp4', '')
    # Parse: {date}_{produk_id}_{platform}.mp4 or {date}_{produk_id}_{acct_id}_{platform}.mp4
    parts = basename.split('_')
    
    # Look for matching MUSIC_ file
    music_patterns = []
    for f in os.listdir(platform_dir):
        if f.startswith('MUSIC_') and (f.endswith('.mp3') or f.endswith('.wav')):
            music_patterns.append(f)
    
    return len(music_patterns) > 0


def run_qc(video_dir):
    print(f"Running Advanced QC Engine on {video_dir}...")
    
    if not os.path.exists(video_dir):
        print(f"Error: {video_dir} not found.")
        return
    
    # Also check images
    img_dir = "engine/data/images"
    
    videos = []
    # Search recursively in subfolders (yt, tt, fb)
    for root, dirs, files in os.walk(video_dir):
        for f in files:
            if f.endswith('.mp4'):
                videos.append(os.path.join(root, f))
    
    hashes = {}
    failed = []
    warnings = []

    # --- PRE-CHECK: Images ---
    print("\n--- Pre-Check: Product Images ---")
    if os.path.exists(img_dir):
        images = [f for f in os.listdir(img_dir) if f.endswith(('.jpg', '.png', '.jpeg'))]
        placeholder_count = 0
        real_count = 0
        
        for img_file in images:
            img_path = os.path.join(img_dir, img_file)
            if is_placeholder_image(img_path):
                placeholder_count += 1
                print(f"  [WARN] {img_file}: Placeholder image detected (low color variance)")
            else:
                real_count += 1
                print(f"  [OK] {img_file}: Real product image")
        
        if real_count == 0 and placeholder_count > 0:
            warnings.append("ALL product images are placeholders â€” video visuals will be poor")
            print(f"  [!!] WARNING: All {placeholder_count} images are placeholders!")
    else:
        warnings.append("Image directory not found")
        print(f"  [!!] Image directory '{img_dir}' not found!")

    # --- PRE-CHECK: Music ---
    print("\n--- Pre-Check: Background Music ---")
    music_found = False
    for platform in ['yt', 'tt', 'fb']:
        platform_dir = os.path.join(video_dir, platform)
        if os.path.exists(platform_dir):
            music_files = [f for f in os.listdir(platform_dir) 
                          if f.startswith('MUSIC_') and (f.endswith('.mp3') or f.endswith('.wav'))]
            if music_files:
                music_found = True
                print(f"  [OK] {platform.upper()}: {len(music_files)} music tracks found")
            else:
                print(f"  [WARN] {platform.upper()}: No per-video music files found")
    
    # Check shared music fallback
    shared_music = "engine/assets/background_music.mp3"
    if os.path.exists(shared_music):
        size = os.path.getsize(shared_music)
        if size < 50000:  # Less than 50KB = probably placeholder
            if not music_found:
                warnings.append("No per-video music AND shared music is a tiny placeholder")
                print(f"  [WARN] Shared music is only {size} bytes â€” likely placeholder")
        else:
            print(f"  [OK] Shared music: {size // 1024}KB")
            music_found = True
    elif not music_found:
        warnings.append("No music files found at all")
        print(f"  [WARN] No music files found anywhere!")

    # --- VIDEO CHECKS ---
    print(f"\n--- Video Quality Checks ({len(videos)} videos) ---")

    # Per-platform duration rules (with tolerance margin)
    DURATION_RULES = {
        '_yt_long':  {'min': 85,  'max': 125, 'label': 'YT Long (90-120s)'},
        '_yt':       {'min': 40,  'max': 55,  'label': 'YT Short (45-50s)'},
        '_tt_short': {'min': 10,  'max': 20,  'label': 'TT Short (15s)'},
        '_tt':       {'min': 20,  'max': 35,  'label': 'TT (25-30s)'},
        '_fb_short': {'min': 18,  'max': 30,  'label': 'FB Short (25s)'},
        '_fb':       {'min': 45,  'max': 65,  'label': 'FB (50-60s)'},
    }
    MIN_FILE_SIZE = 1000 * 1024  # 1MB â€” 4000k bitrate video should be much larger

    def get_duration_rule(filename):
        """Match filename to platform duration rule."""
        # Check longer patterns first to avoid partial matches
        for suffix in ['_yt_long', '_tt_short', '_fb_short', '_yt', '_tt', '_fb']:
            if suffix in filename:
                return DURATION_RULES[suffix]
        return {'min': 5, 'max': 300, 'label': 'Unknown'}

    for path in videos:
        filename = os.path.basename(path)
        print(f"\nChecking: {filename}")

        # 1. File Size Check
        file_size = os.path.getsize(path)
        if file_size == 0:
            print(f"  [FAIL] Empty file")
            failed.append(path)
            continue

        if file_size < MIN_FILE_SIZE:
            print(f"  [FAIL] File too small: {file_size // 1024}KB (min 500KB)")
            failed.append(path)
            continue

        print(f"  [OK] Size: {file_size // 1024}KB")

        # 2. Technical Check (ffprobe)
        try:
            info = get_video_info(path)
            streams = info.get('streams', [])
            v_stream = next((s for s in streams if s['codec_type'] == 'video'), None)
            a_stream = next((s for s in streams if s['codec_type'] == 'audio'), None)

            if not v_stream:
                print(f"  [FAIL] No video stream found")
                failed.append(path)
                continue

            width = int(v_stream['width'])
            height = int(v_stream['height'])
            duration = float(info['format']['duration'])

            # 9:16 Resolution Check
            if width != 1080 or height != 1920:
                print(f"  [FAIL] Wrong resolution: {width}x{height} (expected 1080x1920)")
                failed.append(path)
                continue

            print(f"  [OK] Resolution: {width}x{height}")

            # Bitrate Quality Check (CRF 20 output should be â‰¥1500kbps)
            total_bitrate = int(info['format'].get('bit_rate', 0))
            bitrate_kbps = total_bitrate // 1000 if total_bitrate else 0
            if bitrate_kbps > 0 and bitrate_kbps < 1500:
                print(f"  [FAIL] Bitrate too low: {bitrate_kbps}kbps (min 1500kbps for 1080p clarity)")
                failed.append(path)
                continue

            if bitrate_kbps > 0:
                print(f"  [OK] Bitrate: {bitrate_kbps}kbps")

            # Per-Platform Duration Check
            rule = get_duration_rule(filename)
            if duration < rule['min']:
                print(f"  [FAIL] Duration too short: {duration:.1f}s (expected {rule['label']})")
                failed.append(path)
                continue
            elif duration > rule['max']:
                print(f"  [FAIL] Duration too long: {duration:.1f}s (expected {rule['label']})")
                failed.append(path)
                continue

            print(f"  [OK] Duration: {duration:.1f}s â†’ {rule['label']}")

            # Audio Check (MANDATORY â€” music must be mixed)
            if a_stream:
                print(f"  [OK] Audio: {a_stream.get('codec_name', 'unknown')}")
            else:
                print(f"  [FAIL] No audio stream â€” music not mixed in")
                failed.append(path)
                continue

            # 3. Uniqueness Check (MD5)
            v_hash = get_md5(path)
            if v_hash in hashes:
                print(f"  [FAIL] Duplicate content with {hashes[v_hash]}")
                failed.append(path)
            else:
                hashes[v_hash] = filename
                print(f"  [OK] Unique content")

        except Exception as e:
            print(f"  [FAIL] ffprobe error: {e}")
            failed.append(path)
            continue

    # --- VISUAL SIMILARITY CHECK ---
    print(f"\n--- Visual Similarity Check ---")
    SAMPLE_TIMES = ['1', '5', '9']  # Hook, masalah, solusi scenes
    frame_signatures = {}
    
    for path in videos:
        filename = os.path.basename(path)
        try:
            all_sigs = []
            for ts in SAMPLE_TIMES:
                frame_path = path + f".qc_frame_{ts}.jpg"
                subprocess.run(
                    ['ffmpeg', '-y', '-ss', ts, '-i', path, '-frames:v', '1',
                     '-q:v', '5', frame_path],
                    capture_output=True, timeout=10
                )
                if os.path.exists(frame_path):
                    img = Image.open(frame_path).convert('RGB').resize((64, 64))
                    pixels = list(img.getdata())
                    sig = []
                    for by in range(4):
                        for bx in range(4):
                            block_r, block_g, block_b = 0, 0, 0
                            count = 0
                            for y in range(by*16, (by+1)*16):
                                for x in range(bx*16, (bx+1)*16):
                                    p = pixels[y*64 + x]
                                    block_r += p[0]; block_g += p[1]; block_b += p[2]
                                    count += 1
                            sig.append((block_r//count, block_g//count, block_b//count))
                    all_sigs.extend(sig)
                    os.remove(frame_path)
            if all_sigs:
                frame_signatures[filename] = all_sigs
        except:
            pass

    # Compare signatures pairwise (averaged across all sampled timestamps)
    sig_list = list(frame_signatures.items())
    for i in range(len(sig_list)):
        for j in range(i+1, len(sig_list)):
            name_a, sig_a = sig_list[i]
            name_b, sig_b = sig_list[j]
            if len(sig_a) == len(sig_b) and len(sig_a) > 0:
                total_diff = 0
                for (ra, ga, ba), (rb, gb, bb) in zip(sig_a, sig_b):
                    total_diff += abs(ra-rb) + abs(ga-gb) + abs(ba-bb)
                max_diff = 255 * 3 * len(sig_a)
                similarity = 1.0 - (total_diff / max_diff)
                if similarity > 0.95:
                    warnings.append(f"Visual similarity {similarity:.0%}: {name_a} â†” {name_b}")
                    print(f"  [WARN] {name_a} â†” {name_b}: {similarity:.0%} similar")
    
    if not frame_signatures:
        print(f"  [SKIP] No frames extracted for similarity check")
    elif not any("Visual similarity" in w for w in warnings):
        print(f"  [OK] All {len(frame_signatures)} videos are visually distinct")

    # --- FINAL SUMMARY ---
    print(f"\n{'='*60}")
    print(f"QC SUMMARY")
    print(f"{'='*60}")
    print(f"  Videos checked: {len(videos)}")
    print(f"  Passed: {len(videos) - len(failed)}")
    print(f"  Failed: {len(failed)}")
    print(f"  Warnings: {len(warnings)}")
    
    if warnings:
        print(f"\n  Warnings:")
        for w in warnings:
            print(f"    âš  {w}")
    
    # AUTO-DELETE failed videos so pipeline can regenerate them
    if failed:
        print(f"\n  Failed files (AUTO-DELETING for regeneration):")
        deleted = 0
        for f in failed:
            fname = os.path.basename(f)
            try:
                os.remove(f)
                deleted += 1
                print(f"    x DELETED: {fname}")
            except Exception as e:
                print(f"    x DELETE FAILED: {fname} â€” {e}")
        
        print(f"\n  {deleted} non-compliant videos deleted â†’ will regenerate on next run")
        
        # Save QC report for debugging
        report_path = os.path.join(video_dir, "_qc_report.json")
        report = {
            'checked': len(videos),
            'passed': len(videos) - len(failed),
            'failed': len(failed),
            'deleted': deleted,
            'warnings': warnings,
            'failed_files': [os.path.basename(f) for f in failed],
        }
        with open(report_path, 'w') as rf:
            json.dump(report, rf, indent=2)
        print(f"  QC report saved: {report_path}")
    else:
        print(f"\n[PASS] All {len(videos)} videos passed QC [OK]")


if __name__ == "__main__":
    run_qc("engine/output")
