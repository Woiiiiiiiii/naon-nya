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

# Import auto-restock from music_downloader
try:
    from engine.modules.music_downloader import restock_category as _restock, count_local as _count
    HAS_DOWNLOADER = True
except ImportError:
    HAS_DOWNLOADER = False
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
ENTRY_OFFSETS = [0, 10, 20, 30]


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


def _select_music_from_library(category, produk_id, account_id):
    """Select a music file from local library based on category.
    PREFERS API-downloaded files (.mp3/.ogg) over synth (.wav with _synth_).
    Returns path to selected file or None if no files available."""
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

    # Use deterministic-but-varied selection based on product+account
    seed = int(hashlib.md5(f"{produk_id}_{account_id}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    if api_files:
        print(f"      [INFO] {len(api_files)} API tracks, {len(synth_files)} synth tracks -> using API")
        return rng.choice(api_files)
    elif synth_files:
        print(f"      [INFO] No API tracks, using synth ({len(synth_files)} available)")
        return rng.choice(synth_files)
    return rng.choice(files)


def _process_music_file(source_path, output_path, target_duration, produk_id, account_id):
    """Process a music file: random entry point, trim/loop to target duration, convert to MP3.
    Per instruction: variasi entry point (0, 10, 20, 30s) untuk fingerprint audio."""
    import subprocess

    seed = int(hashlib.md5(
        f"{produk_id}_{account_id}_{datetime.datetime.now().strftime('%Y%m%d')}".encode()
    ).hexdigest()[:8], 16)
    rng = random.Random(seed)
    entry_offset = rng.choice(ENTRY_OFFSETS)

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
                cmd = [
                    'ffmpeg', '-y', '-ss', str(actual_offset),
                    '-i', source_path, '-t', str(target_duration),
                    '-b:a', '192k', '-ar', '44100',
                    '-af', 'equalizer=f=100:width_type=o:width=2:g=5,equalizer=f=8000:width_type=o:width=2:g=-4,'
                           'afade=t=in:st=0:d=0.5,afade=t=out:st=' +
                           str(target_duration - 1) + ':d=1',
                    output_path
                ]
            else:
                # Source too short: loop it
                loops = int(target_duration / max(source_duration, 1)) + 2
                filter_str = (
                    f"aloop=loop={loops}:size={int(source_duration * 44100)},"
                    f"atrim=start={actual_offset}:end={actual_offset + target_duration},"
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
# ═══════════════════════════════════════════════════════════════════

SCALES = {
    'major':      [0, 2, 4, 5, 7, 9, 11],
    'minor':      [0, 2, 3, 5, 7, 8, 10],
    'pentatonic': [0, 2, 4, 7, 9],
    'dorian':     [0, 2, 3, 5, 7, 9, 10],
    'mixolydian': [0, 2, 4, 5, 7, 9, 10],
}

CATEGORY_MOODS = {
    'gadget':   {'tempo': (125, 148), 'density': 0.82, 'wave': 'warm',
                 'bass_v': 0.44, 'pad_v': 0.18, 'mel_v': 0.16, 'perc_v': 0.08, 'scale': 'major'},
    'home':     {'tempo': (85, 105), 'density': 0.50, 'wave': 'sine',
                 'bass_v': 0.38, 'pad_v': 0.30, 'mel_v': 0.13, 'perc_v': 0.05, 'scale': 'pentatonic'},
    'fashion':  {'tempo': (112, 135), 'density': 0.72, 'wave': 'warm',
                 'bass_v': 0.40, 'pad_v': 0.24, 'mel_v': 0.17, 'perc_v': 0.07, 'scale': 'major'},
    'beauty':   {'tempo': (72, 92), 'density': 0.40, 'wave': 'sine',
                 'bass_v': 0.34, 'pad_v': 0.35, 'mel_v': 0.11, 'perc_v': 0.03, 'scale': 'pentatonic'},
    'wellness': {'tempo': (120, 145), 'density': 0.80, 'wave': 'warm',
                 'bass_v': 0.42, 'pad_v': 0.20, 'mel_v': 0.15, 'perc_v': 0.09, 'scale': 'mixolydian'},
}
DEFAULT_MOOD = {'tempo': (110, 132), 'density': 0.70, 'wave': 'warm',
                'bass_v': 0.40, 'pad_v': 0.22, 'mel_v': 0.15, 'perc_v': 0.07, 'scale': 'major'}


def midi_to_freq(m):
    return 440.0 * (2.0 ** ((m - 69) / 12.0))


def make_env(n, a=0.08, d=0.10, s=0.60, r=0.20):
    env = []
    ai, di, ri = int(n*a), int(n*d), int(n*r)
    for i in range(n):
        if i < ai: e = (i / max(ai, 1)) ** 0.7
        elif i < ai+di: e = 1.0 - (1.0-s)*((i-ai)/max(di, 1))
        elif i > n-ri: e = s*((n-i)/max(ri, 1))**1.3
        else: e = s
        env.append(e)
    return env


def osc(freq, t, wt='sine'):
    p = 2*math.pi*freq*t
    if wt == 'sine': return math.sin(p)
    elif wt == 'warm':
        return 0.70*math.sin(p)+0.16*math.sin(p*2)+0.09*math.sin(p*3)+0.05*math.sin(p*4)
    elif wt == 'pad':
        return (0.40*math.sin(p)+0.28*math.sin(2*math.pi*freq*1.004*t)+
                0.20*math.sin(2*math.pi*freq*0.996*t)+0.12*math.sin(p*0.5))
    elif wt == 'bass': return math.tanh(1.4*math.sin(p))
    return math.sin(p)


def _generate_procedural_track(output_path, produk_id, account_id, category='home', duration=15):
    """Generate procedural music as fallback when no library files available."""
    seed = int(hashlib.md5(
        f"{produk_id}_{account_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M')}".encode()
    ).hexdigest()[:8], 16)
    rng = random.Random(seed)

    mood = CATEGORY_MOODS.get(category, DEFAULT_MOOD)
    tempo = rng.randint(*mood['tempo'])
    scale = SCALES[mood.get('scale', 'major')]
    root = rng.choice(list(range(48, 72)))
    beat = 60.0 / tempo

    n = int(SAMPLE_RATE * duration)

    # Generate bass
    bass = [0.0] * n
    t, note_idx = 0.0, 0
    bass_notes = [root-12, root-12+scale[2%len(scale)], root-12+scale[4%len(scale)], root-12]
    while t < duration:
        note = bass_notes[note_idx % len(bass_notes)]
        nd = min(beat, duration - t)
        if nd > 0.01:
            ns = int(SAMPLE_RATE * nd)
            env = make_env(ns, a=0.03, r=0.15)
            si = int(SAMPLE_RATE * t)
            for j in range(min(ns, n-si)):
                bass[si+j] += osc(midi_to_freq(note), j/SAMPLE_RATE, 'bass') * mood['bass_v'] * env[j]
        t += beat
        note_idx += 1

    # Generate pad
    pad = [0.0] * n
    chord_dur = duration / 4
    for ci in range(4):
        cr = root + scale[(ci*2) % len(scale)]
        nd = min(chord_dur, duration - ci*chord_dur)
        if nd <= 0: break
        ns = int(SAMPLE_RATE * nd)
        env = make_env(ns, a=0.18, d=0.05, s=0.75, r=0.22)
        idx = int(SAMPLE_RATE * ci * chord_dur)
        for iv in [0, scale[2%len(scale)], scale[4%len(scale)]]:
            freq = midi_to_freq(cr + iv)
            vol = mood['pad_v'] * (0.50 if iv == 0 else 0.35)
            for j in range(min(ns, n - idx)):
                pad[idx+j] += osc(freq, j/SAMPLE_RATE, 'pad') * vol * env[j]

    # Generate melody
    melody = [0.0] * n
    pool = [root+s for s in scale] + [root+12+s for s in scale]
    t, prev = 0.0, root
    while t < duration:
        if rng.random() < mood['density']:
            cands = [nn for nn in pool if abs(nn-prev) <= 5]
            note = rng.choice(cands or pool)
            prev = note
            nd = beat * rng.choice([0.25, 0.5, 1.0])
            nd = min(nd, duration-t)
            if nd > 0.01:
                ns = int(SAMPLE_RATE*nd)
                env = make_env(ns)
                si = int(SAMPLE_RATE*t)
                for j in range(min(ns, n-si)):
                    melody[si+j] += osc(midi_to_freq(note), j/SAMPLE_RATE, mood['wave']) * mood['mel_v'] * env[j]
        t += beat * rng.choice([0.5, 1])

    # Mix stereo
    left = [0.0] * n
    right = [0.0] * n
    for i in range(n):
        left[i] = bass[i]*1.3 + pad[i]*0.85 + melody[i]*0.35
        right[i] = bass[i]*1.3 + pad[i]*0.58 + melody[i]*0.55

    # Limiter
    peak = max(max(abs(s) for s in left), max(abs(s) for s in right))
    if peak > 0.78:
        r = 0.76 / peak
        left = [s*r for s in left]
        right = [s*r for s in right]

    # Save WAV
    wav_path = output_path.replace('.mp3', '.wav')
    with wave.open(wav_path, 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        for i in range(n):
            l = max(-1.0, min(1.0, left[i]))
            rv = max(-1.0, min(1.0, right[i]))
            wf.writeframes(struct.pack('<h', int(l*32767)))
            wf.writeframes(struct.pack('<h', int(rv*32767)))

    # Convert to MP3
    try:
        import subprocess
        res = subprocess.run(
            ['ffmpeg', '-y', '-i', wav_path, '-b:a', '192k', '-ar', '44100', output_path],
            capture_output=True, text=True, timeout=60
        )
        if res.returncode == 0:
            os.remove(wav_path)
    except Exception:
        pass

    return f"procedural_{mood.get('scale', 'major')}_{tempo}bpm"


# ═══════════════════════════════════════════════════════════════════
#  MAIN: Generate Music for All Videos
# ═══════════════════════════════════════════════════════════════════

def generate_all_music(queue_dir, output_dir):
    """Generate music for every video in the queue.
    Auto-downloads from Freesound/Pixabay if stock is low. ZERO manual process."""
    print("=== Music Generator (Auto-Download: Freesound + Pixabay) ===")
    print(f"  Music library: {os.path.abspath(MUSIC_DIR)}")
    print(f"  Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # Auto-restock ALL categories before processing
    categories_needed = set()

    platforms = {
        'yt': os.path.join(queue_dir, 'yt_queue.jsonl'),
        'tt': os.path.join(queue_dir, 'tt_queue.jsonl'),
        'fb': os.path.join(queue_dir, 'fb_queue.jsonl'),
    }

    # Collect which categories we need
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
                    categories_needed.add(mapped)

    # ALWAYS try to restock from APIs (don't trust synth-based stock count)
    if HAS_DOWNLOADER and categories_needed:
        print("  Force-restocking music from APIs (Freesound + Pixabay)...")
        for cat in sorted(categories_needed):
            print(f"    [{cat}] Forcing API download...")
            _restock(cat)
            new_stock = _count(cat)
            # Show API vs synth breakdown
            folder = _get_music_folder(cat)
            api_count = sum(1 for f in os.listdir(folder)
                          if f.lower().endswith(('.mp3', '.ogg', '.m4a'))
                          and '_synth_' not in f)
            synth_count = sum(1 for f in os.listdir(folder)
                            if '_synth_' in f)
            print(f"    [{cat}] Stock: {new_stock} total ({api_count} API, {synth_count} synth)")
        print()

    # Show library status after restock
    for cat in sorted(categories_needed):
        files = _list_music_files(cat)
        status = f"{len(files)} files" if files else "EMPTY (will use procedural)"
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

            # Determine target duration
            if platform == 'yt' and video_type == 'long':
                target_dur = MUSIC_DURATIONS.get('yt_long', 120)
            else:
                target_dur = MUSIC_DURATIONS.get(platform, 50)

            # PRIORITY 1: Auto-downloaded library files
            library_file = _select_music_from_library(category, produk_id, acct_id)

            if library_file:
                success = _process_music_file(
                    library_file, music_file, target_dur, produk_id, acct_id
                )
                if success:
                    print(f"    [LIBRARY] {os.path.basename(music_file)} <- {os.path.basename(library_file)} ({target_dur}s)")
                    total_lib += 1
                    continue

            # PRIORITY 2: Procedural fallback (last resort)
            info = _generate_procedural_track(
                music_file, produk_id, acct_id, category, duration=target_dur
            )
            print(f"    [SYNTH] {os.path.basename(music_file)} | {info} ({target_dur}s)")
            total_proc += 1

    print(f"\n=== Music Complete: {total_lib} from library, {total_proc} procedural ===")


if __name__ == "__main__":
    generate_all_music("engine/queue", "engine/output")

