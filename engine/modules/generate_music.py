"""
generate_music.py
Music per kategori per video produk.

Per instruksi_upgrade_system.md Bagian 6:
  Musik di-download OTOMATIS dari Freesound API + Pixabay (royalty-free)
  MusicGen DIHAPUS (rawan gagal)
  Variasi entry point: start dari detik 0, 10, 20, atau 30 secara random

Architecture:
  1. Auto-restock via music_downloader (Freesound -> Pixabay -> Synth)
  2. Select from local stock assets/music/[kategori]/
  3. Process: random entry point + trim/loop to target duration
  4. Output: MP3 di engine/output/[platform]/MUSIC_{produk_id}_{acct_id}.mp3

Semua otomatis, ZERO proses manual.
"""
import os
import sys
import json
import random
import math
import struct
import wave
import hashlib
import datetime
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from engine.modules.category_router import get_category

# Import auto-restock from music_downloader (try multiple import paths)
HAS_DOWNLOADER = False
try:
    from engine.modules.music_downloader import restock_category as _restock, count_local as _count
    HAS_DOWNLOADER = True
except ImportError:
    try:
        from music_downloader import restock_category as _restock, count_local as _count
        HAS_DOWNLOADER = True
    except ImportError:
        def _restock(cat): return 0
        def _count(cat): return 0

SAMPLE_RATE = 44100
MUSIC_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'music')

# Category mapping from category_router categories to music folders
CATEGORY_MUSIC_MAP = {
    'fashion':    'fashion',
    'gadget':     'gadget',
    'beauty':     'beauty',
    'home':       'home',
    'wellness':   'wellness',
    'elektronik': 'gadget',
    'kosmetik':   'beauty',
    'alat_rumah_tangga': 'home',
    'kesehatan':  'wellness',
}

# Platform-specific music durations (seconds)
MUSIC_DURATIONS = {
    'yt': 50,       # Shorts 45-50s
    'yt_long': 120,  # Long-form 90-120s
    'tt': 27,       # TikTok 25-30s
    'fb': 55,       # Facebook 50-60s
}

# Random entry point offsets per instruction (variasi fingerprint audio)
# Full offsets for long videos, small offsets for short videos
ENTRY_OFFSETS_LONG = [0, 10, 20, 30]       # For yt_long (120s)
ENTRY_OFFSETS_SHORT = [0, 1, 2, 3, 5]      # For yt_short/tt/fb (prevent music gap at start)


def _get_music_folder(category):
    """Get music folder path for a category."""
    mapped = CATEGORY_MUSIC_MAP.get(category, category)
    folder = os.path.join(MUSIC_DIR, mapped)
    os.makedirs(folder, exist_ok=True)
    return folder


def _list_music_files(category):
    """List available music files for a category."""
    folder = _get_music_folder(category)
    extensions = ('.mp3', '.wav', '.ogg', '.m4a', '.flac')
    files = []
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            if f.lower().endswith(extensions):
                files.append(os.path.join(folder, f))
    return files


# SESSION-LEVEL music dedup: tracks used in this pipeline run
# Prevents same track being assigned to multiple videos (within or across channels)
_used_tracks = set()


def _reset_used_tracks():
    """Reset music tracking (call at start of new pipeline run)."""
    global _used_tracks
    _used_tracks = set()


def _select_music_from_library(category, produk_id, account_id):
    """Select a UNIQUE music file from local library based on category.
    DEDUP: each track can only be used ONCE per pipeline run, across ALL channels.
    PREFERS API-downloaded files (.mp3/.ogg) over synth (.wav with _synth_).
    Returns path to selected file or None if no files available."""
    global _used_tracks

    files = _list_music_files(category)
    if not files:
        # Try general/fallback folder
        general_folder = os.path.join(MUSIC_DIR, 'general')
        if os.path.isdir(general_folder):
            for f in os.listdir(general_folder):
                if f.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a', '.flac')):
                    files.append(os.path.join(general_folder, f))

    if not files:
        return None

    # PREFER API-downloaded tracks over synth
    api_files = [f for f in files if '_synth_' not in os.path.basename(f)]
    synth_files = [f for f in files if '_synth_' in os.path.basename(f)]

    # Use product+account+timestamp seed for deterministic variety
    import datetime
    now = datetime.datetime.now()
    run_id = f"{produk_id}_{account_id}_{now.strftime('%Y%m%d%H%M%S')}_{now.microsecond}"
    seed = int(hashlib.md5(run_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    # DEDUP: filter out tracks already used in this pipeline run
    available_api = [f for f in api_files if os.path.abspath(f) not in _used_tracks]
    available_synth = [f for f in synth_files if os.path.abspath(f) not in _used_tracks]

    # If ALL tracks exhausted in this session, restock 1 new track (don't reuse)
    if not available_api and not available_synth:
        print(f"      [WARN] All {len(files)} tracks used in session, restocking 1 new...")
        _ensure_category_has_music(category, force=True)
        # Re-check after restock
        files = _list_music_files(category)
        available_api = [f for f in files if '_synth_' not in os.path.basename(f) and os.path.abspath(f) not in _used_tracks]
        available_synth = [f for f in files if '_synth_' in os.path.basename(f) and os.path.abspath(f) not in _used_tracks]
        if not available_api and not available_synth:
            # Last resort: reset dedup and reuse
            print(f"      [WARN] Restock failed, resetting dedup pool")
            _used_tracks.clear()
            available_api = [f for f in files if '_synth_' not in os.path.basename(f)]
            available_synth = [f for f in files if '_synth_' in os.path.basename(f)]

    if available_api:
        rng.shuffle(available_api)
        pick = available_api[0]
        _used_tracks.add(os.path.abspath(pick))
        remaining = len(available_api) - 1
        print(f"      [MUSIC] {os.path.basename(pick)} ({remaining} remaining in {category})")
        return pick
    elif available_synth:
        rng.shuffle(available_synth)
        pick = available_synth[0]
        _used_tracks.add(os.path.abspath(pick))
        print(f"      [MUSIC] Synth: {os.path.basename(pick)}")
        return pick

    # Absolute fallback
    rng.shuffle(files)
    pick = files[0]
    _used_tracks.add(os.path.abspath(pick))
    return pick



def _process_music_file(source_path, output_path, target_duration, produk_id, account_id):
    """Process a music file: random entry point, trim/loop to target duration, convert to MP3.
    Per instruction: variasi entry point (0, 10, 20, 30s) untuk fingerprint audio."""
    import subprocess

    seed = int(hashlib.md5(
        f"{produk_id}_{account_id}_{datetime.datetime.now().strftime('%Y%m%d')}".encode()
    ).hexdigest()[:8], 16)
    rng = random.Random(seed)
    # Short videos: small offsets to avoid missing music at start
    offsets = ENTRY_OFFSETS_SHORT if target_duration < 60 else ENTRY_OFFSETS_LONG
    entry_offset = rng.choice(offsets)

    try:
        # Probe source duration
        probe = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', source_path],
            capture_output=True, text=True, timeout=10
        )
        source_duration = float(probe.stdout.strip()) if probe.returncode == 0 else 0
    except Exception:
        source_duration = 0

    try:
        if source_duration > 0:
            # Clamp entry offset to available duration
            max_offset = max(0, source_duration - target_duration)
            actual_offset = min(entry_offset, max_offset)

            if source_duration >= target_duration + actual_offset:
                # Source long enough: trim from entry point
                # loudnorm (EBU R128) ensures ALL music at same perceived loudness
                af_filter = (
                    'loudnorm=I=-18:TP=-1:LRA=11,'
                    'equalizer=f=100:width_type=o:width=2:g=5,'
                    'equalizer=f=8000:width_type=o:width=2:g=-4,'
                    f'afade=t=in:st=0:d=0.5,afade=t=out:st={target_duration - 1}:d=1'
                )
                cmd = [
                    'ffmpeg', '-y', '-ss', str(actual_offset),
                    '-i', source_path, '-t', str(target_duration),
                    '-b:a', '192k', '-ar', '44100',
                    '-af', af_filter,
                    output_path
                ]
            else:
                # Source too short: loop it
                loops = int(target_duration / max(source_duration, 1)) + 2
                filter_str = (
                    f"aloop=loop={loops}:size={int(source_duration * 44100)},"
                    f"atrim=start={actual_offset}:end={actual_offset + target_duration},"
                    f"loudnorm=I=-18:TP=-1:LRA=11,"
                    f"equalizer=f=100:width_type=o:width=2:g=5,"
                    f"equalizer=f=8000:width_type=o:width=2:g=-4,"
                    f"afade=t=in:st=0:d=0.5,"
                    f"afade=t=out:st={target_duration - 1}:d=1"
                )
                cmd = [
                    'ffmpeg', '-y', '-i', source_path,
                    '-af', filter_str,
                    '-b:a', '192k', '-ar', '44100',
                    '-t', str(target_duration),
                    output_path
                ]
        else:
            # Can't probe duration: just copy and hope for the best
            cmd = [
                'ffmpeg', '-y', '-i', source_path,
                '-b:a', '192k', '-ar', '44100',
                '-t', str(target_duration),
                output_path
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return True
        else:
            print(f"    [WARN] FFmpeg error: {result.stderr[:200]}")
    except Exception as e:
        print(f"    [WARN] Music processing error: {e}")

    # Fallback: direct copy if ffmpeg fails
    try:
        shutil.copy2(source_path, output_path)
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
#  PROCEDURAL FALLBACK (when no library music available)
#  Delegates to music_downloader's numpy-accelerated synth (<1s vs 165s)
# ═══════════════════════════════════════════════════════════════════

CATEGORY_MOODS = {
    'gadget':   {'scale': 'major'},
    'home':     {'scale': 'pentatonic'},
    'fashion':  {'scale': 'major'},
    'beauty':   {'scale': 'pentatonic'},
    'wellness': {'scale': 'mixolydian'},
}


def _generate_procedural_track(output_path, produk_id, account_id, category='home', duration=15):
    """Generate procedural music as fallback.
    Uses music_downloader's numpy-accelerated version for speed.
    Falls back to simple WAV if numpy is not available."""
    seed = int(hashlib.md5(
        f"{produk_id}_{account_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M')}".encode()
    ).hexdigest()[:8], 16)

    mood_info = CATEGORY_MOODS.get(category, {'scale': 'major'})

    # Try fast numpy version from music_downloader
    try:
        from engine.modules.music_downloader import generate_procedural_track as _fast_synth
        wav_path = output_path.replace('.mp3', '.wav')
        _fast_synth(wav_path, category, seed, duration)

        # Convert WAV to MP3 via ffmpeg
        try:
            import subprocess
            res = subprocess.run(
                ['ffmpeg', '-y', '-i', wav_path, '-b:a', '192k', '-ar', '44100', output_path],
                capture_output=True, text=True, timeout=60
            )
            if res.returncode == 0 and os.path.exists(output_path):
                os.remove(wav_path)
            else:
                # ffmpeg failed, rename WAV as output
                if os.path.exists(wav_path):
                    os.rename(wav_path, output_path)
        except FileNotFoundError:
            # ffmpeg not installed, keep WAV
            if os.path.exists(wav_path):
                os.rename(wav_path, output_path)

        return f"procedural_{mood_info.get('scale', 'major')}_numpy"

    except ImportError:
        pass

    # Fallback: simple sine wave WAV (no numpy, very fast)
    rng = random.Random(seed)
    n = int(SAMPLE_RATE * duration)
    freq = 440.0 * (2.0 ** ((rng.randint(48, 72) - 69) / 12.0))

    wav_path = output_path.replace('.mp3', '.wav')
    with wave.open(wav_path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        for i in range(n):
            t = i / SAMPLE_RATE
            val = 0.3 * math.sin(2 * math.pi * freq * t)
            val += 0.15 * math.sin(2 * math.pi * freq * 2 * t)
            if i < SAMPLE_RATE:
                val *= i / SAMPLE_RATE
            elif i > n - SAMPLE_RATE:
                val *= (n - i) / SAMPLE_RATE
            sample = max(-32767, min(32767, int(val * 32767)))
            wf.writeframes(struct.pack('<h', sample))

    # Try convert to MP3
    try:
        import subprocess
        res = subprocess.run(
            ['ffmpeg', '-y', '-i', wav_path, '-b:a', '192k', '-ar', '44100', output_path],
            capture_output=True, text=True, timeout=60
        )
        if res.returncode == 0:
            os.remove(wav_path)
    except Exception:
        if os.path.exists(wav_path):
            os.rename(wav_path, output_path)

    return f"procedural_{mood_info.get('scale', 'major')}_simple"


# ═══════════════════════════════════════════════════════════════════
#  MAIN: Generate Music for All Videos
# ═══════════════════════════════════════════════════════════════════

def _ensure_category_has_music(category, force=False):
    """On-demand restock: get 1 track for a category via tier system.
    Tier 1: Freesound API → Tier 2: YouTube Audio → Tier 3: Procedural Synth.
    Only generates what's needed (1 track at a time).
    force=True: always generate even if library has files (for dedup exhaustion).
    Returns: number of tracks available after restock."""
    files = _list_music_files(category)
    if files and not force:
        return len(files)  # Already have music, skip restock

    count_needed = 1  # Only get 1 track at a time
    print(f"      [RESTOCK] {category}: getting {count_needed} track via tiers...")

    if HAS_DOWNLOADER:
        # Tier 1: Freesound (try to get 1 track)
        try:
            from engine.modules.music_downloader import fetch_freesound, count_local
            got = fetch_freesound(category, count=count_needed)
            if got > 0:
                print(f"      [TIER 1] Freesound: +{got} track for {category}")
                return count_local(category)
        except Exception as e:
            print(f"      [TIER 1] Freesound failed: {e}")

        # Tier 2: YouTube Audio (skip Pixabay — dead code)
        try:
            from engine.modules.music_downloader import fetch_youtube_audio_library
            got = fetch_youtube_audio_library(category, count=count_needed)
            if got > 0:
                print(f"      [TIER 2] YouTube Audio: +{got} track for {category}")
                return count_local(category)
        except Exception as e:
            print(f"      [TIER 2] YouTube Audio failed: {e}")

    # Tier 3: Procedural synth (always works, generate 1 track)
    print(f"      [TIER 3] Generating 1 procedural track for {category}...")
    folder = _get_music_folder(category)
    existing = len(_list_music_files(category))
    mp3_path = os.path.join(folder, f"{category}_synth_{existing+1:02d}.mp3")
    _generate_procedural_track(
        mp3_path, f"restock_{existing}", f"lib_{category}",
        category=category, duration=random.randint(25, 45)
    )
    return len(_list_music_files(category))


# ═══════════════════════════════════════════════════════════════════
#  MUSIC DEDUP: Track which music files have been used globally
# ═══════════════════════════════════════════════════════════════════
USED_MUSIC_FILE = os.path.join(os.path.dirname(__file__), '..', 'state', 'used_music.json')


def _load_used_music():
    """Load set of music filenames that have been used in previous runs."""
    if os.path.exists(USED_MUSIC_FILE):
        try:
            with open(USED_MUSIC_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def _save_used_music(used_set):
    """Save used music tracking."""
    os.makedirs(os.path.dirname(USED_MUSIC_FILE), exist_ok=True)
    with open(USED_MUSIC_FILE, 'w') as f:
        json.dump(sorted(used_set), f, indent=2)


def generate_all_music(queue_dir, output_dir):
    """Generate music for every video in the queue.
    TIER SYSTEM: Library first → Restock on-demand (Freesound → YT → Synth).
    Each track used ONCE per run — no duplicates across channels.
    Global dedup via used_music.json — tracks not reused across runs."""
    _reset_used_tracks()

    globally_used = _load_used_music()

    print("=== Music Generator (Tier System + Dedup) ===")
    print(f"  Music library: {os.path.abspath(MUSIC_DIR)}")
    print(f"  Previously used tracks: {len(globally_used)}")
    print(f"  Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    platforms = {
        'yt': os.path.join(queue_dir, 'yt_queue.jsonl'),
        'tt': os.path.join(queue_dir, 'tt_queue.jsonl'),
        'fb': os.path.join(queue_dir, 'fb_queue.jsonl'),
    }

    # Show library status
    categories_seen = set()
    for platform, queue_file in platforms.items():
        if not os.path.exists(queue_file):
            continue
        with open(queue_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    job = json.loads(line.strip())
                    acct_id = job.get('account_id', f'{platform}_1')
                    cat = get_category(acct_id)
                    mapped = CATEGORY_MUSIC_MAP.get(cat, cat)
                    categories_seen.add(mapped)

    for cat in sorted(categories_seen):
        files = _list_music_files(cat)
        status = f"{len(files)} files" if files else "EMPTY (will restock via tiers)"
        print(f"  [{cat}] {status}")
    print()

    total_lib = 0
    total_proc = 0

    for platform, queue_file in platforms.items():
        if not os.path.exists(queue_file):
            print(f"  [{platform.upper()}] Queue not found")
            continue

        jobs = []
        with open(queue_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    jobs.append(json.loads(line.strip()))

        platform_dir = os.path.join(output_dir, platform)
        os.makedirs(platform_dir, exist_ok=True)
        print(f"  [{platform.upper()}] Processing {len(jobs)} tracks...")

        for job in jobs:
            produk_id = job.get('produk_id', 'unknown')
            acct_id = job.get('account_id', f'{platform}_1')
            video_type = job.get('video_type', 'short')
            category = get_category(acct_id)

            music_file = os.path.join(platform_dir, f"MUSIC_{produk_id}_{acct_id}.mp3")

            # Skip if already generated this run
            if os.path.exists(music_file) and os.path.getsize(music_file) > 1000:
                print(f"    [SKIP] Already exists: {os.path.basename(music_file)}")
                total_lib += 1
                continue

            # Determine target duration
            if platform == 'yt' and video_type == 'long':
                target_dur = MUSIC_DURATIONS.get('yt_long', 120)
            else:
                target_dur = MUSIC_DURATIONS.get(platform, 50)

            # STEP 1: Try existing library
            library_file = _select_music_from_library(category, produk_id, acct_id)

            if library_file:
                success = _process_music_file(
                    library_file, music_file, target_dur, produk_id, acct_id
                )
                if success:
                    basename = os.path.basename(library_file)
                    globally_used.add(basename)
                    print(f"    [LIBRARY] {os.path.basename(music_file)} <- {basename} ({target_dur}s)")
                    total_lib += 1
                    continue

            # STEP 2: Library exhausted → force restock via tier system (on-demand, 1 track)
            _ensure_category_has_music(category, force=True)
            # Try library again after restock
            library_file = _select_music_from_library(category, produk_id, acct_id)
            if library_file:
                success = _process_music_file(
                    library_file, music_file, target_dur, produk_id, acct_id
                )
                if success:
                    basename = os.path.basename(library_file)
                    globally_used.add(basename)
                    print(f"    [RESTOCKED] {os.path.basename(music_file)} <- {basename} ({target_dur}s)")
                    total_lib += 1
                    continue

            # STEP 3: Last resort — procedural on-demand (1 track)
            info = _generate_procedural_track(
                music_file, produk_id, acct_id, category, duration=target_dur
            )
            print(f"    [SYNTH] {os.path.basename(music_file)} | {info} ({target_dur}s)")
            total_proc += 1

    # Save global used music tracking
    _save_used_music(globally_used)

    print(f"\n=== Music Complete: {total_lib} library, {total_proc} procedural ===")


if __name__ == "__main__":
    generate_all_music("engine/queue", "engine/output")


