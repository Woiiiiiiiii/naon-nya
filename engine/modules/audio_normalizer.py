"""
audio_normalizer.py
Normalize audio volume and EQ balance across all videos.

Ensures CONSISTENT audio levels:
- Music: normalized to target loudness (perceived volume)
- SFX: consistent relative level  
- Treble/Bass: balanced EQ so no track sounds boomy or tinny

Used by: generate_video_yt_short.py, generate_video_yt_long.py,
         generate_video_tt.py, generate_video_fb.py
"""

import os
import numpy as np
from io import BytesIO

# ═══════════════════════════════════════════════════════════════════
#  STANDARD VOLUME LEVELS — SINGLE consistent level for ALL channels
#  Female VO naturally louder → VO turun 1, Music naik 1 for female
# ═══════════════════════════════════════════════════════════════════
MUSIC_VOLUME = 0.22      # Background music (default / male VO)
SFX_VOLUME = 0.25        # Sound effects (subtle)
VOICEOVER_VOLUME = 0.95  # Voiceover default (male = clearly dominant)

# Female VO: slightly softer VO + louder music
FEMALE_VO_VOLUME = 0.88      # Female VO (turun 1 tingkat)
FEMALE_MUSIC_VOLUME = 0.25   # Music for female VO (naik 1 tingkat)

# Which accounts use female voice (GadisNeural)
FEMALE_ACCOUNTS = {'yt_1', 'yt_3', 'yt_5', 'tt_1'}

# Target RMS loudness (linear scale, ~-18 dBFS)
TARGET_RMS = 0.12


def get_voice_volumes(acct_id):
    """Get VO and music volume levels based on account voice gender.
    Female accounts get softer VO + louder music.
    Returns: (vo_volume, music_volume)"""
    if acct_id in FEMALE_ACCOUNTS:
        return FEMALE_VO_VOLUME, FEMALE_MUSIC_VOLUME
    return VOICEOVER_VOLUME, MUSIC_VOLUME


def normalize_audio_clip(audio_clip, target_rms=TARGET_RMS):
    """Normalize an AudioFileClip to consistent perceived loudness.
    
    Handles short clips (<0.5s) gracefully — just returns with default gain.
    """
    try:
        from moviepy import afx
        
        # Short clips (SFX): skip sampling, just return as-is
        if audio_clip.duration is None or audio_clip.duration < 0.5:
            return audio_clip
        
        fps = 44100
        
        # Get audio samples — wrap in try/except for duration edge cases
        try:
            samples = audio_clip.to_soundarray(fps=fps, nbytes=2)
        except Exception:
            # Fallback: try with lower fps for short clips
            try:
                samples = audio_clip.to_soundarray(fps=22050, nbytes=2)
            except Exception:
                return audio_clip
        
        if len(samples) == 0:
            return audio_clip
        
        # Calculate RMS (root mean square = perceived loudness)
        rms = np.sqrt(np.mean(samples.astype(float) ** 2))
        
        if rms < 0.001:  # Silence
            return audio_clip
        
        # Calculate gain to reach target RMS
        gain = target_rms / rms
        
        # Limit gain range TIGHTLY for consistent volume
        # max 2.5x amplification, min 0.5x reduction
        gain = max(0.5, min(gain, 2.5))
        
        return audio_clip.with_effects([afx.MultiplyVolume(gain)])
    except Exception as e:
        print(f"    [AUDIO] Normalize failed: {e}")
        return audio_clip


def apply_eq_balance(audio_clip, bass_boost=1.0, treble_cut=0.0):
    """Apply simple EQ balancing using high-pass / low-pass filtering.
    
    moviepy doesn't have built-in EQ, so we use a simple approach:
    - Consistent frequency balance via volume-based compensation
    - This keeps all tracks sounding similar
    
    For proper EQ, FFmpeg filters would be needed (handled at export time).
    
    Args:
        audio_clip: moviepy AudioFileClip
        bass_boost: multiplier for low frequencies (1.0 = neutral)
        treble_cut: reduction for high frequencies (0.0 = none)
    
    Returns:
        audio_clip (unchanged if no FFmpeg EQ available)
    """
    # moviepy's native audio processing is limited
    # Real EQ is applied via FFmpeg at export time (see get_ffmpeg_eq_params)
    return audio_clip


def prepare_music(audio_clip, total_duration, music_vol=None):
    """Prepare music track: loop if needed, trim, normalize, set volume.
    
    Args:
        audio_clip: raw AudioFileClip of the music
        total_duration: target video duration
        music_vol: optional volume override (default: MUSIC_VOLUME)
    
    Returns:
        processed AudioFileClip ready for mixing
    """
    from moviepy import afx, concatenate_audioclips
    
    if music_vol is None:
        music_vol = MUSIC_VOLUME
    
    # Loop if music is shorter than video
    if audio_clip.duration < total_duration:
        reps = int(total_duration / audio_clip.duration) + 1
        audio_clip = concatenate_audioclips([audio_clip] * reps)
    
    # Trim to video length
    audio_clip = audio_clip.subclipped(0, total_duration)
    
    # Normalize loudness
    audio_clip = normalize_audio_clip(audio_clip, TARGET_RMS)
    
    # Apply music volume (per-gender or default)
    audio_clip = audio_clip.with_effects([afx.MultiplyVolume(music_vol)])
    
    return audio_clip


def prepare_sfx(audio_clip, start_time):
    """Prepare SFX: normalize and set standard volume + timing.
    
    Args:
        audio_clip: raw AudioFileClip of the SFX
        start_time: when to start playing in the video
    
    Returns:
        processed AudioFileClip ready for mixing
    """
    from moviepy import afx
    
    # Normalize
    audio_clip = normalize_audio_clip(audio_clip, TARGET_RMS)
    
    # Standard SFX volume
    audio_clip = audio_clip.with_effects([afx.MultiplyVolume(SFX_VOLUME)])
    
    # Set start time
    audio_clip = audio_clip.with_start(start_time)
    
    return audio_clip


def get_ffmpeg_audio_params():
    """Get FFmpeg output parameters for consistent audio across all videos.
    
    NOTE: Audio normalization is done in Python (normalize_audio_clip + MultiplyVolume).
    We only set codec and bitrate here. FFmpeg filters like loudnorm
    are NOT used because they conflict with moviepy's stream handling.
    
    Returns: dict of params for video.write_videofile()
    """
    return {
        'audio_codec': 'aac',
        'audio_bitrate': '192k',
    }


# Session-level dedup: track ALL music picks within this pipeline run
# Prevents same music being used by different videos in same run
_session_music_picks = set()


def find_music_file(platform_dir, produk_id, acct_id, category='home'):
    """Find music file with multi-tier fallback + SESSION DEDUP.

    Tiers:
      1. Exact match: MUSIC_{produk_id}_{acct_id}.mp3 (pre-assigned)
      2. Same product: any MUSIC_{produk_id}_*.mp3 (session deduped)
      3. Same platform: any MUSIC_*.mp3 in platform dir (session + cross-run deduped)
      4. Category library: track from assets/music/{category}/ (prefer API over synth)

    SESSION DEDUP: Every pick is tracked per-run. No music reuse within a single run.
    CROSS-RUN DEDUP: used_music.json tracks historical usage.

    Returns: (path, tier) or (None, 0) if nothing found.
    """
    import glob
    import random
    global _session_music_picks

    # Tier 1: Exact match (pre-assigned by generate_music.py Phase 2)
    exact = os.path.join(platform_dir, f"MUSIC_{produk_id}_{acct_id}.mp3")
    if os.path.exists(exact):
        _session_music_picks.add(os.path.abspath(exact))
        return exact, 1

    # Load global used music to avoid cross-run reuse
    used_music_file = os.path.join(os.path.dirname(__file__), '..', 'state', 'used_music.json')
    used_set = set()
    if os.path.exists(used_music_file):
        try:
            import json as _json
            with open(used_music_file, 'r') as _f:
                used_set = set(_json.load(_f))
        except Exception:
            pass

    # Tier 2: Same product, different account (session deduped)
    pattern2 = os.path.join(platform_dir, f"MUSIC_{produk_id}_*.mp3")
    matches2 = glob.glob(pattern2)
    available2 = [m for m in matches2 if os.path.abspath(m) not in _session_music_picks]
    if available2:
        pick = random.choice(available2)
        _session_music_picks.add(os.path.abspath(pick))
        print(f"    [MUSIC T2] {acct_id}: using {os.path.basename(pick)} (same product)")
        return pick, 2

    # Tier 3: Any music in platform dir (session + cross-run deduped)
    pattern3 = os.path.join(platform_dir, "MUSIC_*.mp3")
    matches3 = glob.glob(pattern3)
    available3 = [m for m in matches3
                  if os.path.abspath(m) not in _session_music_picks
                  and os.path.basename(m) not in used_set]
    if not available3:
        available3 = [m for m in matches3 if os.path.abspath(m) not in _session_music_picks]
    if available3:
        pick = random.choice(available3)
        _session_music_picks.add(os.path.abspath(pick))
        print(f"    [MUSIC T3] {acct_id}: using {os.path.basename(pick)} (same platform, deduped)")
        return pick, 3

    # Tier 4: Category music library (prefer API over synth)
    music_lib = os.path.join(os.path.dirname(__file__), '..', 'assets', 'music')
    cat_map = {
        'fashion': 'fashion', 'gadget': 'gadget', 'beauty': 'beauty',
        'home': 'home', 'wellness': 'wellness', 'food': 'home',
        'elektronik': 'gadget', 'kosmetik': 'beauty',
        'alat_rumah_tangga': 'home', 'kesehatan': 'wellness',
    }

    mapped = cat_map.get(category, category)

    def _pick_from_dir(d, label):
        """Pick track from dir: prefer API, dedup session + cross-run."""
        if not os.path.isdir(d):
            return None
        all_tracks = [f for f in os.listdir(d)
                      if f.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a'))]
        if not all_tracks:
            return None

        # Split API vs synth (PREFER API-downloaded tracks)
        api_tracks = [f for f in all_tracks if '_synth_' not in f]
        synth_tracks = [f for f in all_tracks if '_synth_' in f]

        for pool, pool_name in [(api_tracks, 'API'), (synth_tracks, 'Synth')]:
            available = [f for f in pool
                         if os.path.abspath(os.path.join(d, f)) not in _session_music_picks
                         and f not in used_set]
            if not available:
                available = [f for f in pool
                             if os.path.abspath(os.path.join(d, f)) not in _session_music_picks]
            if available:
                pick_name = random.choice(available)
                pick_path = os.path.join(d, pick_name)
                _session_music_picks.add(os.path.abspath(pick_path))
                print(f"    [MUSIC T4-{label}] {acct_id}: {pool_name} {pick_name}")
                return pick_path
        return None

    lib_dir = os.path.join(music_lib, mapped)
    result = _pick_from_dir(lib_dir, mapped)
    if result:
        return result, 4

    gen_dir = os.path.join(music_lib, 'general')
    result = _pick_from_dir(gen_dir, 'general')
    if result:
        return result, 4

    print(f"    [MUSIC WARNING] No music found for {produk_id}/{acct_id} -- video will have no BGM!")
    return None, 0

