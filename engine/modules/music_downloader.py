"""
music_downloader.py
Auto-download royalty-free music per kategori.

Per user request: MusicGen DIHAPUS (rawan gagal).
Sumber musik otomatis:
  Tier 1: Freesound API (proper REST API, search+download, royalty-free)
  Tier 2: Pixabay Music (web scraping, royalty-free)
  Tier 3: Procedural wave synthesis (offline fallback)

Organizes by category in assets/music/[category]/.
Min 5 tracks per category. Auto-restock when below threshold.
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
        print(f"    [SKIP] FREESOUND_API_KEY not set")
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
            'page_size': min(count + 5, 15),
            'sort': 'rating_desc',
            'token': api_key,
        }

        print(f"    [FREESOUND] Searching: '{query}'...")
        resp = requests.get(url, params=params, timeout=30)

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
    """Fetch music from Pixabay MUSIC API (Tier 2).
    PENTING: endpoint /api/music/ bukan /api/ (itu untuk gambar!)"""
    api_key = os.environ.get('PIXABAY_API_KEY', '')
    if not api_key:
        print(f"    [SKIP] PIXABAY_API_KEY not set")
        return 0

    d = get_music_dir(category)
    mood = CATEGORY_MOODS.get(category, CATEGORY_MOODS['fashion'])
    query = mood.get('pixabay_query', 'background music')
    downloaded = 0

    try:
        # Pixabay MUSIC API (BUKAN images!)
        url = "https://pixabay.com/api/music/"
        params = {
            'key': api_key,
            'q': query,
            'per_page': min(count + 3, 15),
        }

        print(f"    [PIXABAY MUSIC] Searching for '{query}'...")
        resp = requests.get(url, params=params, timeout=30)

        if resp.status_code == 200:
            data = resp.json()
            hits = data.get('hits', [])
            print(f"    [OK] Pixabay Music: {len(hits)} results")

            for hit in hits:
                if downloaded >= count:
                    break

                # Pixabay Music API returns 'audio' field with download URL
                audio_url = hit.get('audio', '')
                if not audio_url:
                    # Fallback fields
                    audio_url = hit.get('url', '') or hit.get('previewURL', '')
                if not audio_url or not audio_url.startswith('http'):
                    continue

                track_num = count_local(category) + 1
                title = hit.get('title', f'track_{track_num}')[:30].replace(' ', '_')
                filename = f"{category}_px_{track_num:02d}_{title}.mp3"
                filepath = os.path.join(d, filename)

                try:
                    audio_resp = requests.get(audio_url, timeout=60)
                    if audio_resp.status_code == 200 and len(audio_resp.content) > 10000:
                        # Validate: check magic bytes to ensure it's audio, not image/HTML
                        header = audio_resp.content[:4]
                        if header[:3] == b'ID3' or header[:2] == b'\xff\xfb' or header[:2] == b'\xff\xf3':  # MP3
                            pass
                        elif header[:4] == b'OggS':  # OGG
                            pass
                        elif header[:4] == b'RIFF':  # WAV
                            pass
                        else:
                            print(f"    [WARN] Pixabay returned non-audio file (magic: {header[:4]}), skipping")
                            continue
                        with open(filepath, 'wb') as f:
                            f.write(audio_resp.content)
                        size_kb = os.path.getsize(filepath) // 1024
                        duration = hit.get('duration', 0)
                        print(f"    [OK] {filename} ({size_kb}KB, {duration}s)")
                        downloaded += 1
                        time.sleep(0.3)
                except Exception as e:
                    print(f"    [WARN] Download failed: {e}")

        elif resp.status_code == 429:
            print(f"    [WARN] Pixabay rate limited")
        else:
            print(f"    [WARN] Pixabay Music API error: {resp.status_code}")

    except Exception as e:
        print(f"    [WARN] Pixabay music fetch error: {e}")

    return downloaded


# ===============================================
# TIER 3: Procedural Wave Synthesis (offline fallback)
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
    """Generate a procedural music track using pure wave synthesis (Tier 3)."""
    rng = random.Random(seed_val)
    mood = CATEGORY_MOODS.get(category, CATEGORY_MOODS['fashion'])

    bpm = mood['bpm'] + rng.randint(-10, 10)
    beat_dur = 60.0 / bpm
    scale = SCALES.get(mood['scale'], SCALES['major'])
    root = mood['root'] + rng.choice([-2, 0, 2])

    n_samples = int(SAMPLE_RATE * duration)
    left = [0.0] * n_samples
    right = [0.0] * n_samples

    # Bass line
    bass_notes = [root - 12 + scale[i % len(scale)] for i in range(4)]
    t, ni = 0.0, 0
    while t < duration:
        note = bass_notes[ni % len(bass_notes)]
        nd = beat_dur
        ns = int(SAMPLE_RATE * min(nd, duration - t))
        si = int(SAMPLE_RATE * t)
        for j in range(min(ns, n_samples - si)):
            env = _envelope(j, ns, 0.02, 0.15)
            v = _osc(_midi_to_freq(note), j / SAMPLE_RATE, 'warm') * 0.25 * env
            left[si + j] += v
            right[si + j] += v
        t += nd
        ni += 1

    # Pad chords
    chord_dur = duration / 4
    for ci in range(4):
        cr = root + scale[(ci * 2) % len(scale)]
        nd = min(chord_dur, duration - ci * chord_dur)
        ns = int(SAMPLE_RATE * nd)
        si = int(SAMPLE_RATE * ci * chord_dur)
        for iv in [0, scale[2 % len(scale)], scale[4 % len(scale)]]:
            freq = _midi_to_freq(cr + iv)
            vol = 0.12 if iv == 0 else 0.08
            for j in range(min(ns, n_samples - si)):
                env = _envelope(j, ns, 0.15, 0.2)
                v = _osc(freq, j / SAMPLE_RATE, 'sine') * vol * env * mood['energy']
                left[si + j] += v * 0.8
                right[si + j] += v * 0.6

    # Melody
    pool = [root + s for s in scale] + [root + 12 + s for s in scale]
    t, prev = 0.0, root
    while t < duration:
        if rng.random() < mood['energy'] * 0.7:
            cands = [nn for nn in pool if abs(nn - prev) <= 5]
            note = rng.choice(cands or pool)
            prev = note
            nd = beat_dur * rng.choice([0.5, 1.0])
            ns = int(SAMPLE_RATE * min(nd, duration - t))
            si = int(SAMPLE_RATE * t)
            for j in range(min(ns, n_samples - si)):
                env = _envelope(j, ns)
                v = _osc(_midi_to_freq(note), j / SAMPLE_RATE, mood['wave']) * 0.08 * env
                left[si + j] += v * 0.5
                right[si + j] += v * 0.9
        t += beat_dur * rng.choice([0.5, 1.0])

    # Normalize
    peak = max(max(abs(s) for s in left), max(abs(s) for s in right), 0.01)
    if peak > 0.75:
        scale_f = 0.72 / peak
        left = [s * scale_f for s in left]
        right = [s * scale_f for s in right]

    # Write WAV
    with wave.open(filepath, 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        for i in range(n_samples):
            l = max(-1.0, min(1.0, left[i]))
            r = max(-1.0, min(1.0, right[i]))
            wf.writeframes(struct.pack('<h', int(l * 32767)))
            wf.writeframes(struct.pack('<h', int(r * 32767)))

    return True


# ===============================================
# MAIN: AUTO-RESTOCK (Freesound -> Pixabay -> Synth)
# ===============================================

def restock_all():
    """Auto-restock music for all categories WITH rotation.
    Each run: delete oldest API tracks → download fresh ones → keep it varied.
    Priority: Freesound API -> Pixabay -> Procedural synth."""
    print("=== Music Auto-Download (with rotation) ===")
    print(f"  Base dir: {os.path.abspath(MUSIC_DIR)}")
    print(f"  Min stock: {MIN_STOCK} per category")
    print(f"  Rotate: {ROTATE_COUNT} tracks per run\n")

    for category in CATEGORY_MOODS:
        d = get_music_dir(category)
        local = count_local(category)
        print(f"  [{category}] Local: {local} tracks")

        # ROTATION: delete oldest API tracks to force variety
        if local >= MIN_STOCK:
            api_files = sorted(
                [f for f in os.listdir(d)
                 if f.lower().endswith(('.mp3', '.ogg', '.m4a'))
                 and '_synth_' not in f],
                key=lambda f: os.path.getmtime(os.path.join(d, f))
            )
            # Delete oldest ROTATE_COUNT API tracks
            to_delete = api_files[:ROTATE_COUNT]
            for f in to_delete:
                try:
                    os.remove(os.path.join(d, f))
                    print(f"    [ROTATE] Deleted old: {f}")
                except Exception:
                    pass
            local = count_local(category)

        need = max(MIN_STOCK - local, ROTATE_COUNT)
        print(f"    Downloading {need} fresh tracks...")

        # -- TIER 1: Freesound API --
        fs_got = fetch_freesound(category, count=need)
        if fs_got > 0:
            print(f"    [+] Freesound: +{fs_got} tracks")

        # -- TIER 2: Pixabay --
        new_local = count_local(category)
        still_need = MIN_STOCK - new_local
        if still_need > 0:
            px_got = fetch_pixabay_music(category, count=still_need)
            if px_got > 0:
                print(f"    [+] Pixabay: +{px_got} tracks")

        # -- TIER 3: Procedural synth (always works) --
        new_local = count_local(category)
        still_need = MIN_STOCK - new_local
        if still_need > 0:
            d = get_music_dir(category)
            generated = 0
            for i in range(still_need):
                track_num = new_local + i + 1
                filename = f"{category}_synth_{track_num:02d}.wav"
                filepath = os.path.join(d, filename)
                if not os.path.exists(filepath):
                    seed_val = hash(f"{category}_{track_num}_{datetime.datetime.now().strftime('%Y%m')}")
                    dur = random.randint(25, 45)
                    generate_procedural_track(filepath, category, seed_val, dur)
                    generated += 1
                    size_kb = os.path.getsize(filepath) // 1024
                    print(f"    [OK] Synth: {filename} ({size_kb}KB)")
            if generated > 0:
                print(f"    [+] Synth fallback: +{generated} tracks")

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
    """Restock a single category.
    ALWAYS tries APIs first (Freesound -> Pixabay).
    Deletes old synth files when API music is available.
    Synth is LAST RESORT only."""
    d = get_music_dir(category)
    local = count_local(category)
    
    # Count existing API vs synth files
    api_count = sum(1 for f in os.listdir(d)
                    if f.lower().endswith(('.mp3', '.ogg', '.m4a'))
                    and '_synth_' not in f)
    synth_count = sum(1 for f in os.listdir(d) if '_synth_' in f)
    
    print(f"    [{category}] Current: {api_count} API, {synth_count} synth")
    
    # ALWAYS try Freesound (even if we have stock)
    need = max(MIN_STOCK - api_count, 2)  # Always try at least 2
    fs_got = fetch_freesound(category, count=need)
    
    # ALWAYS try Pixabay too
    need2 = max(MIN_STOCK - api_count - fs_got, 2)
    px_got = fetch_pixabay_music(category, count=need2)
    
    api_total = fs_got + px_got
    
    # If we got API music, DELETE old synth files (they're inferior)
    if api_total > 0 and synth_count > 0:
        for f in os.listdir(d):
            if '_synth_' in f:
                try:
                    os.remove(os.path.join(d, f))
                    print(f"    [CLEANUP] Deleted old synth: {f}")
                except Exception:
                    pass
    
    # Only generate synth if ZERO music available (APIs both failed)
    new_local = count_local(category)
    if new_local < MIN_STOCK and api_total == 0:
        still_need = MIN_STOCK - new_local
        print(f"    [SYNTH] APIs failed, generating {still_need} procedural tracks...")
        for i in range(still_need):
            track_num = new_local + i + 1
            filepath = os.path.join(d, f"{category}_synth_{track_num:02d}.wav")
            if not os.path.exists(filepath):
                seed_val = hash(f"{category}_{track_num}")
                generate_procedural_track(filepath, category, seed_val, random.randint(25, 45))
    
    return count_local(category)


if __name__ == "__main__":
    restock_all()
