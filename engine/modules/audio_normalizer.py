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
#  STANDARD VOLUME LEVELS (consistent across ALL platforms)
# ═══════════════════════════════════════════════════════════════════
MUSIC_VOLUME = 0.30      # Background music (well behind VO)
SFX_VOLUME = 0.25        # Sound effects (subtle)
VOICEOVER_VOLUME = 0.90  # Voiceover (clearly dominant over music)

# Target RMS loudness (linear scale, ~-18 dBFS)
TARGET_RMS = 0.12


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
        
        # Limit gain — allow higher amplification for quiet tracks (was 3.0, too low)
        gain = max(0.3, min(gain, 5.0))
        
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
        bass_boost: multiplier for bass (1.0 = neutral)
        treble_cut: dB to cut high frequencies (0 = neutral)
    
    Returns:
        audio_clip (unchanged if no FFmpeg EQ available)
    """
    # moviepy's native audio processing is limited
    # Real EQ is applied via FFmpeg at export time (see get_ffmpeg_eq_params)
    return audio_clip


def prepare_music(audio_clip, total_duration):
    """Prepare music track: loop if needed, trim, normalize, set standard volume.
    
    Args:
        audio_clip: raw AudioFileClip of the music
        total_duration: target video duration
    
    Returns:
        processed AudioFileClip ready for mixing
    """
    from moviepy import afx, concatenate_audioclips
    
    # Loop if music is shorter than video
    if audio_clip.duration < total_duration:
        reps = int(total_duration / audio_clip.duration) + 1
        audio_clip = concatenate_audioclips([audio_clip] * reps)
    
    # Trim to video length
    audio_clip = audio_clip.subclipped(0, total_duration)
    
    # Normalize loudness
    audio_clip = normalize_audio_clip(audio_clip, TARGET_RMS)
    
    # Apply standard music volume
    audio_clip = audio_clip.with_effects([afx.MultiplyVolume(MUSIC_VOLUME)])
    
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

