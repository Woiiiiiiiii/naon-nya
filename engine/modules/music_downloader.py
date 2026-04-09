"""
music_downloader.py
Auto-download royalty-free music per kategori.

Per user request: MusicGen DIHAPUS (rawan gagal).
Sumber musik otomatis (3 tier):
  Tier 1: Freesound API (proper REST API, search+download, royalty-free)
  Tier 2: YouTube Audio Library (yt-dlp, curated playlists, royalty-free)
  Tier 3: Procedural wave synthesis (offline fallback, always works)

Pixabay: DIHAPUS (no music API, dead code)

Organizes by category in assets/music/[category]/.
"""
import os
import sys
import json
import random
import math
import wave
import struct
import requests
import datetime
import time

# Minimum stock per category
MIN_STOCK = 12

# How many tracks to rotate each run (delete old + download new)
ROTATE_COUNT = 3

# Base directory for music assets
MUSIC_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'music')

SAMPLE_RATE = 44100

# Category -> mood/query settings for API searches
CATEGORY_MOODS = {
    'fashion': {
        'bpm': 110, 'scale': 'major', 'root': 60, 'wave': 'warm', 'energy': 0.5,
        'freesound_query': 'upbeat pop background music',
        'freesound_tags': 'upbeat,pop,trendy,background',
        'pixabay_query': 'upbeat pop trendy fashion',
    },
    'gadget': {
        'bpm': 115, 'scale': 'minor', 'root': 57, 'wave': 'warm', 'energy': 0.55,
        'freesound_query': 'electronic tech background music',
        'freesound_tags': 'electronic,tech,modern,digital',
        'pixabay_query': 'tech electronic modern',
    },
    'beauty': {
        'bpm': 85, 'scale': 'major', 'root': 64, 'wave': 'sine', 'energy': 0.35,
        'freesound_query': 'soft elegant piano ambient',
        'freesound_tags': 'soft,elegant,piano,ambient',
        'pixabay_query': 'soft elegant piano beauty',
    },
    'home': {
        'bpm': 100, 'scale': 'major', 'root': 62, 'wave': 'warm', 'energy': 0.45,
        'freesound_query': 'cheerful acoustic happy ukulele',
        'freesound_tags': 'cheerful,acoustic,happy,ukulele',
        'pixabay_query': 'cheerful acoustic happy',
    },
    'wellness': {
        'bpm': 72, 'scale': 'pentatonic', 'root': 60, 'wave': 'sine', 'energy': 0.3,
        'freesound_query': 'calm ambient meditation peaceful',
        'freesound_tags': 'calm,ambient,meditation,relaxing',
        'pixabay_query': 'calm ambient meditation',
    },
}

SCALES = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'pentatonic': [0, 2, 4, 7, 9],
}


# ===============================================
# UTILITY FUNCTIONS
# ===============================================

def get_music_dir(category):
    """Get local music directory for a category."""
    d = os.path.join(MUSIC_DIR, category)
    os.makedirs(d, exist_ok=True)
    return d


def count_local(category):
    """Count local music files for a category."""
    d = get_music_dir(category)
    exts = ('.mp3', '.wav', '.ogg', '.m4a', '.flac')
    return sum(1 for f in os.listdir(d) if f.lower().endswith(exts))


def get_random_track(category):
    """Get a random music track for a category. Returns path or None."""
    d = get_music_dir(category)
    exts = ('.mp3', '.wav', '.ogg', '.m4a', '.flac')
    tracks = [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(exts)]
    return random.choice(tracks) if tracks else None


# ===============================================
# TIER 1: Freesound API (royalty-free, proper API)
# ===============================================
# Register at https://freesound.org/apiv2/apply/
# Get API key, set as FREESOUND_API_KEY env var

def fetch_freesound(category, count=3):
    """Fetch music from Freesound API (Tier 1 -- best for automated download)."""
    api_key = os.environ.get('FREESOUND_API_KEY', '')
    if not api_key:
        print(f"    [SKIP] FREESOUND_API_KEY not set in environment")
        print(f"    [HINT] Set FREESOUND_API_KEY env var or GitHub secret")
        return 0

    d = get_music_dir(category)
    mood = CATEGORY_MOODS.get(category, CATEGORY_MOODS['fashion'])
    query = mood.get('freesound_query', 'background music')
    downloaded = 0

    try:
        # Freesound text search API
        url = "https://freesound.org/apiv2/search/text/"
        params = {
            'query': query,
            'filter': 'duration:[30 TO 300] tag:music',
            'fields': 'id,name,previews,duration,tags',
            'page_size': min(count + 10, 15),
            'sort': random.choice(['rating_desc', 'downloads_desc', 'created_desc']),
            'page': random.randint(1, 5),  # Random page for variety
            'token': api_key,
        }

        print(f"    [FREESOUND] Searching: '{query}'...")
        
        # Retry once on timeout (GitHub Actions has high latency to freesound.org)
        resp = None
        for attempt in range(2):
            try:
                resp = requests.get(url, params=params, timeout=60)
                break
            except requests.exceptions.Timeout:
                if attempt == 0:
                    print(f"    [FREESOUND] Timeout (attempt 1/2), retrying...")
                    continue
                else:
                    print(f"    [FREESOUND] Timeout after 2 attempts")
                    return 0
        
        if resp is None:
            return 0

        if resp.status_code == 200:
            data = resp.json()
            results = data.get('results', [])
            print(f"    [OK] Freesound: {len(results)} results (total: {data.get('count', 0)})")

            for sound in results:
                if downloaded >= count:
                    break

                # Get preview MP3 URL (no OAuth needed for previews)
                previews = sound.get('previews', {})
                preview_url = (previews.get('preview-hq-mp3') or
                               previews.get('preview-lq-mp3') or
                               previews.get('preview-hq-ogg', ''))

                if not preview_url:
                    continue

                track_num = count_local(category) + 1
                ext = '.mp3' if 'mp3' in preview_url else '.ogg'
                filename = f"{category}_fs_{track_num:02d}{ext}"
                filepath = os.path.join(d, filename)

                try:
                    audio_resp = requests.get(preview_url, timeout=30)
                    if audio_resp.status_code == 200 and len(audio_resp.content) > 5000:
                        # Validate: check magic bytes to ensure it's audio, not image/HTML
                        header = audio_resp.content[:4]
                        if header[:3] == b'ID3' or header[:2] == b'\xff\xfb' or header[:2] == b'\xff\xf3':  # MP3
                            pass  # Valid MP3
                        elif header[:4] == b'OggS':  # OGG
                            pass  # Valid OGG
                        elif header[:4] == b'RIFF':  # WAV
                            pass  # Valid WAV
                        else:
                            print(f"    [WARN] Skipping non-audio file (magic: {header[:4]})")
                            continue
                        with open(filepath, 'wb') as f:
                            f.write(audio_resp.content)
                        size_kb = os.path.getsize(filepath) // 1024
                        duration = sound.get('duration', 0)
                        print(f"    [OK] {filename} ({size_kb}KB, {duration:.0f}s) - {sound.get('name', '')[:40]}")
                        downloaded += 1
                        time.sleep(0.5)  # Rate limit courtesy
                except Exception as e:
                    print(f"    [WARN] Download failed: {e}")

        elif resp.status_code == 401:
            print(f"    [WARN] Freesound: invalid API key")
        elif resp.status_code == 429:
            print(f"    [WARN] Freesound: rate limited")
        else:
            print(f"    [WARN] Freesound API error: {resp.status_code}")

    except Exception as e:
        print(f"    [WARN] Freesound fetch error: {e}")

    return downloaded


# ===============================================
# TIER 2: Pixabay Music Scraping
# ===============================================

def fetch_pixabay_music(category, count=3):
    """Pixabay does NOT have a music API endpoint.
    Their API only supports images (/api/) and videos (/api/videos/).
    The /api/music/ endpoint was never real — it always returned errors.
    This tier is kept as a placeholder in case Pixabay adds music support.
    Meanwhile, Tier 1 (Freesound) and Tier 3 (YouTube) handle music."""
    print(f"    [SKIP] Pixabay has no music API (only images/videos)")
    return 0


# ===============================================
# TIER 3: YouTube Audio Library (yt-dlp, royalty-free)
# ===============================================
# Downloads audio from YouTube search using royalty-free queries.
# Uses yt-dlp for reliable audio extraction.

# Category -> YouTube search queries (royalty-free music keywords)
YT_AUDIO_QUERIES = {
    'fashion': 'upbeat pop royalty free background music no copyright',
    'gadget': 'electronic tech royalty free background music no copyright',
    'beauty': 'soft piano ambient royalty free background music no copyright',
    'home': 'cheerful acoustic ukulele royalty free background music no copyright',
    'wellness': 'calm meditation ambient royalty free background music no copyright',
}


def fetch_youtube_audio_library(category, count=3):
    """Fetch royalty-free music from YouTube via yt-dlp (Tier 2).
    Downloads audio-only from YouTube search results matching royalty-free queries.
    Requires: pip install yt-dlp"""
    try:
        import subprocess
        # Quick availability check — use python import, NOT subprocess
        # (yt-dlp --version hangs on Windows and some CI environments)
        try:
            import yt_dlp
            print(f"    [YT] yt-dlp available (python module)")
        except ImportError:
            print(f"    [SKIP] yt-dlp not installed (pip install yt-dlp)")
            return 0
    except Exception:
        print(f"    [SKIP] yt-dlp check failed")
        return 0

    d = get_music_dir(category)
    query = YT_AUDIO_QUERIES.get(category, 'royalty free background music no copyright')
    downloaded = 0

    try:
        import subprocess

        print(f"    [YT AUDIO] Searching: '{query}'...")

        # Use yt-dlp to search and download audio-only
        # --default-search ytsearch: search YouTube
        # --max-downloads: limit results
        # --extract-audio: audio only
        # --audio-format mp3: convert to mp3
        # --audio-quality 5: medium quality (smaller files)
        # --match-filter: only short tracks (30s-300s for background music)
        # --no-playlist: don't expand playlists
        # -o: output template
        track_num_start = count_local(category) + 1

        for i in range(count):
            if downloaded >= count:
                break

            track_num = track_num_start + downloaded
            filename = f"{category}_yt_{track_num:02d}.mp3"
            filepath = os.path.join(d, filename)

            if os.path.exists(filepath):
                continue

            # Use random offset + unique search variations for truly different results
            search_variations = [
                query,
                f'{query} 2024',
                f'{query} instrumental',
                f'{query} loop',
                f'{query} creative commons',
            ]
            search_q = random.choice(search_variations)
            # ytsearchN returns Nth result — use larger offsets for variety
            offset = random.randint(1, 20)
            search_query = f"ytsearch{offset}:{search_q}"

            cmd = [
                'yt-dlp',
                '--no-playlist',
                '--no-update',
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', '5',
                '--match-filter', 'duration >= 20 & duration <= 600',
                '--max-downloads', '1',
                '-o', filepath.replace('.mp3', '.%(ext)s'),
                '--no-overwrites',
                search_query,
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

                if result.returncode != 0 and result.stderr:
                    # Show first line of error for debugging
                    err_line = result.stderr.strip().split('\n')[0][:100]
                    print(f"    [WARN] yt-dlp error: {err_line}")

                # yt-dlp may save with different extension, find the actual file
                base = filepath.replace('.mp3', '')
                actual_file = None
                for ext in ['.mp3', '.m4a', '.ogg', '.wav', '.opus']:
                    candidate = base + ext
                    if os.path.exists(candidate):
                        actual_file = candidate
                        break

                if actual_file and os.path.getsize(actual_file) > 10000:
                    # Rename to standard .mp3 name if different
                    if actual_file != filepath:
                        os.rename(actual_file, filepath)

                    size_kb = os.path.getsize(filepath) // 1024
                    # Hash-check: reject if identical to existing file
                    import hashlib as _hl
                    with open(filepath, 'rb') as _fh:
                        new_hash = _hl.md5(_fh.read()).hexdigest()
                    is_dup = False
                    for existing_f in os.listdir(d):
                        ef = os.path.join(d, existing_f)
                        if ef == filepath or not os.path.isfile(ef):
                            continue
                        with open(ef, 'rb') as _fh2:
                            if _hl.md5(_fh2.read()).hexdigest() == new_hash:
                                print(f"    [DUP] {filename} identical to {existing_f}, deleting")
                                os.remove(filepath)
                                is_dup = True
                                break
                    if not is_dup:
                        print(f"    [OK] {filename} ({size_kb}KB)")
                        downloaded += 1
                    time.sleep(1)  # Rate limit courtesy
                else:
                    # Clean up any partial downloads
                    for ext in ['.mp3', '.m4a', '.ogg', '.wav', '.opus', '.part', '.temp']:
                        candidate = base + ext
                        if os.path.exists(candidate):
                            os.remove(candidate)

            except subprocess.TimeoutExpired:
                print(f"    [WARN] yt-dlp timeout for track {i+1}")
            except Exception as e:
                print(f"    [WARN] yt-dlp download error: {e}")

    except Exception as e:
        print(f"    [WARN] YouTube audio fetch error: {e}")

    return downloaded


# ===============================================
# TIER 4: Procedural Wave Synthesis (offline fallback)
# ===============================================

def _midi_to_freq(note):
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def _osc(freq, t, wave_type='sine'):
    p = 2 * math.pi * freq * t
    if wave_type == 'sine':
        return math.sin(p)
    elif wave_type == 'warm':
        return 0.7*math.sin(p) + 0.15*math.sin(2*p) + 0.08*math.sin(3*p) + 0.05*math.sin(4*p)
    elif wave_type == 'square':
        return 1.0 if math.sin(p) > 0 else -1.0
    return math.sin(p)


def _envelope(i, n, attack=0.05, release=0.2):
    ai = int(n * attack)
    ri = int(n * release)
    if i < ai:
        return i / max(ai, 1)
    elif i > n - ri:
        return (n - i) / max(ri, 1)
    return 1.0


def generate_procedural_track(filepath, category, seed_val=0, duration=30):
    """Generate a procedural music track using numpy-accelerated wave synthesis.
    FAST: uses numpy vectorized ops instead of per-sample Python loops.
    Generates 30s stereo WAV in <1 second."""
    import numpy as np

    rng = random.Random(seed_val)
    mood = CATEGORY_MOODS.get(category, CATEGORY_MOODS['fashion'])

    bpm = mood['bpm'] + rng.randint(-10, 10)
    beat_dur = 60.0 / bpm
    sc = SCALES.get(mood['scale'], SCALES['major'])
    root = mood['root'] + rng.choice([-2, 0, 2])

    n = int(SAMPLE_RATE * duration)
    t_arr = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    left = np.zeros(n, dtype=np.float64)
    right = np.zeros(n, dtype=np.float64)

    def add_tone(target_l, target_r, freq, start_s, dur_s, vol_l, vol_r, attack=0.05, release=0.2):
        """Add a tone to L/R arrays using vectorized numpy."""
        si = int(start_s * SAMPLE_RATE)
        ns = int(dur_s * SAMPLE_RATE)
        if si >= n or ns <= 0:
            return
        ns = min(ns, n - si)
        t = np.arange(ns, dtype=np.float64) / SAMPLE_RATE
        # Envelope
        ai = max(int(ns * attack), 1)
        ri = max(int(ns * release), 1)
        env = np.ones(ns)
        env[:ai] = np.linspace(0, 1, ai)
        env[-ri:] = np.linspace(1, 0, ri)
        # Oscillator (warm = fundamental + harmonics)
        sig = np.sin(2 * np.pi * freq * t) * 0.7
        sig += np.sin(4 * np.pi * freq * t) * 0.15
        sig += np.sin(6 * np.pi * freq * t) * 0.08
        sig *= env
        target_l[si:si+ns] += sig * vol_l
        target_r[si:si+ns] += sig * vol_r

    # Bass line
    bass_notes = [root - 12 + sc[i % len(sc)] for i in range(4)]
    t_pos, ni = 0.0, 0
    while t_pos < duration:
        note = bass_notes[ni % len(bass_notes)]
        freq = _midi_to_freq(note)
        nd = min(beat_dur, duration - t_pos)
        add_tone(left, right, freq, t_pos, nd, 0.25, 0.25, attack=0.02, release=0.15)
        t_pos += beat_dur
        ni += 1

    # Pad chords
    chord_dur = duration / 4
    for ci in range(4):
        cr = root + sc[(ci * 2) % len(sc)]
        nd = min(chord_dur, duration - ci * chord_dur)
        for iv in [0, sc[2 % len(sc)], sc[4 % len(sc)]]:
            freq = _midi_to_freq(cr + iv)
            vol = 0.12 * mood['energy'] if iv == 0 else 0.08 * mood['energy']
            add_tone(left, right, freq, ci * chord_dur, nd, vol * 0.8, vol * 0.6,
                     attack=0.15, release=0.2)

    # Melody
    pool = [root + s for s in sc] + [root + 12 + s for s in sc]
    t_pos, prev = 0.0, root
    while t_pos < duration:
        if rng.random() < mood['energy'] * 0.7:
            cands = [nn for nn in pool if abs(nn - prev) <= 5]
            note = rng.choice(cands or pool)
            prev = note
            nd = beat_dur * rng.choice([0.5, 1.0])
            nd = min(nd, duration - t_pos)
            freq = _midi_to_freq(note)
            add_tone(left, right, freq, t_pos, nd, 0.04, 0.07)
        t_pos += beat_dur * rng.choice([0.5, 1.0])

    # Normalize
    peak = max(np.max(np.abs(left)), np.max(np.abs(right)), 0.01)
    if peak > 0.75:
        scale_f = 0.72 / peak
        left *= scale_f
        right *= scale_f

    # Clip
    left = np.clip(left, -1.0, 1.0)
    right = np.clip(right, -1.0, 1.0)

    # Write WAV (numpy → int16 → bytes, fast)
    l_int = (left * 32767).astype(np.int16)
    r_int = (right * 32767).astype(np.int16)
    stereo = np.column_stack((l_int, r_int))

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with wave.open(filepath, 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(stereo.tobytes())

    return True


# ===============================================
# MAIN: AUTO-RESTOCK (Freesound -> Pixabay -> YT Audio -> Synth)
# ===============================================

def restock_all():
    """Auto-restock music for all categories.
    Uses restock_category() which has correct tier order:
    Freesound -> YouTube -> Synth (Pixabay REMOVED)."""
    print("=== Music Auto-Restock (3 tiers) ===")
    print(f"  Base dir: {os.path.abspath(MUSIC_DIR)}")
    print(f"  Min stock: {MIN_STOCK} per category\n")

    for category in CATEGORY_MOODS:
        local = count_local(category)
        print(f"  [{category}] Current: {local} tracks")
        restock_category(category)
        final = count_local(category)
        print(f"    Final stock: {final} tracks")

    # Summary
    print("\n  === Music Library Summary ===")
    total = 0
    for cat in CATEGORY_MOODS:
        c = count_local(cat)
        total += c
        status = "OK" if c >= MIN_STOCK else "LOW"
        print(f"    [{status}] {cat}: {c} tracks")
    print(f"    Total: {total} tracks")


def restock_category(category):
    """Restock a single category ONLY if stock is below MIN_STOCK.
    If stock >= MIN_STOCK → immediately return (no API calls).
    Tries APIs in order: Freesound → YouTube Audio.
    Synth is LAST RESORT only (when ALL API tiers failed)."""
    d = get_music_dir(category)
    local = count_local(category)
    
    # FAST PATH: if we already have enough tracks, skip everything
    if local >= MIN_STOCK:
        print(f"    [{category}] Stock OK: {local} tracks (min={MIN_STOCK}), skipping restock")
        return local
    
    # Count existing API vs synth files
    api_count = sum(1 for f in os.listdir(d)
                    if f.lower().endswith(('.mp3', '.ogg', '.m4a'))
                    and '_synth_' not in f)
    synth_count = sum(1 for f in os.listdir(d) if '_synth_' in f)
    
    print(f"    [{category}] Current: {api_count} API, {synth_count} synth (need {MIN_STOCK - local} more)")
    
    need = MIN_STOCK - local
    api_total = 0

    # -- TIER 1: Freesound API --
    if need > 0:
        fs_got = fetch_freesound(category, count=need)
        api_total += fs_got
        if fs_got > 0:
            print(f"    [+] Freesound: +{fs_got} tracks")
        need -= fs_got

    # -- TIER 2: YouTube Audio Library (only if Tier 1 didn't get enough) --
    if need > 0:
        yt_got = fetch_youtube_audio_library(category, count=need)
        api_total += yt_got
        if yt_got > 0:
            print(f"    [+] YouTube Audio: +{yt_got} tracks")
        need -= yt_got
    
    # Only generate synth if we STILL don't have enough
    new_local = count_local(category)
    if new_local < MIN_STOCK:
        still_need = MIN_STOCK - new_local
        print(f"    [SYNTH] Generating {still_need} procedural tracks...")
        for i in range(still_need):
            track_num = new_local + i + 1
            filepath = os.path.join(d, f"{category}_synth_{track_num:02d}.wav")
            if not os.path.exists(filepath):
                seed_val = hash(f"{category}_{track_num}")
                generate_procedural_track(filepath, category, seed_val, random.randint(25, 45))
    
    return count_local(category)


if __name__ == "__main__":
    restock_all()
