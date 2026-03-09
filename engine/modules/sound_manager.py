"""
sound_manager.py
Generate sound effects (SFX) for video transitions and reveals.

Pure Python synthesis — no pydub or external libraries needed.
Same approach as generate_music.py: wave + struct + math.

Effects:
  - whoosh:     frequency sweep for transitions (0.4s)
  - ding:       high ping for feature reveals (0.3s)
  - pop:        short pop for text appearance (0.2s)
  - swoosh:     quick sweep for slide-in (0.3s)
  - bass_drop:  low freq impact for price reveal (0.5s)
  - tick:       subtle tick for counting (0.1s)

All cached to engine/assets/sounds/ — generated once, reused.
"""
import os
import sys
import math
import wave
import struct
import random

SAMPLE_RATE = 44100
SOUNDS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'sounds')


def _save_wav(samples, filepath):
    """Save mono float samples to WAV file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with wave.open(filepath, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        for s in samples:
            s = max(-1.0, min(1.0, s))
            wf.writeframes(struct.pack('<h', int(s * 32767)))


def _envelope(n, attack=0.05, release=0.3):
    """Simple attack-release envelope."""
    env = []
    a_samples = int(SAMPLE_RATE * attack)
    r_samples = int(SAMPLE_RATE * release)
    for i in range(n):
        if i < a_samples:
            env.append(i / max(a_samples, 1))
        elif i > n - r_samples:
            env.append((n - i) / max(r_samples, 1))
        else:
            env.append(1.0)
    return env


def generate_whoosh(duration=0.4, volume=0.6):
    """Frequency sweep — whoosh for transitions."""
    n = int(SAMPLE_RATE * duration)
    samples = [0.0] * n
    env = _envelope(n, attack=0.02, release=0.15)

    for i in range(n):
        t = i / SAMPLE_RATE
        progress = i / n
        # Sweep from 200Hz to 4000Hz
        freq = 200 + 3800 * progress ** 0.5
        # White noise + sweep
        noise = random.uniform(-0.3, 0.3)
        sweep = math.sin(2 * math.pi * freq * t) * 0.7
        samples[i] = (sweep + noise) * env[i] * volume

    return samples


def generate_ding(duration=0.3, volume=0.5):
    """High-pitched ping — feature reveals."""
    n = int(SAMPLE_RATE * duration)
    samples = [0.0] * n
    env = _envelope(n, attack=0.01, release=0.25)

    freq = 1800  # High ping
    for i in range(n):
        t = i / SAMPLE_RATE
        # Main tone + harmonic
        s = math.sin(2 * math.pi * freq * t) * 0.6
        s += math.sin(2 * math.pi * freq * 2 * t) * 0.2
        s += math.sin(2 * math.pi * freq * 3 * t) * 0.1
        samples[i] = s * env[i] * volume

    return samples


def generate_pop(duration=0.15, volume=0.5):
    """Short pop — text appearance."""
    n = int(SAMPLE_RATE * duration)
    samples = [0.0] * n
    env = _envelope(n, attack=0.005, release=0.10)

    for i in range(n):
        t = i / SAMPLE_RATE
        progress = i / n
        # Quick frequency drop from 800 to 200
        freq = 800 - 600 * progress
        s = math.sin(2 * math.pi * freq * t)
        samples[i] = s * env[i] * volume

    return samples


def generate_swoosh(duration=0.3, volume=0.5):
    """Quick sweep — slide-in animation."""
    n = int(SAMPLE_RATE * duration)
    samples = [0.0] * n
    env = _envelope(n, attack=0.02, release=0.12)

    for i in range(n):
        t = i / SAMPLE_RATE
        progress = i / n
        # Sweep up from 300 to 2000
        freq = 300 + 1700 * progress ** 0.7
        noise = random.uniform(-0.2, 0.2)
        s = math.sin(2 * math.pi * freq * t) * 0.5 + noise * 0.3
        samples[i] = s * env[i] * volume

    return samples


def generate_bass_drop(duration=0.5, volume=0.7):
    """Low frequency impact — price reveal."""
    n = int(SAMPLE_RATE * duration)
    samples = [0.0] * n
    env = _envelope(n, attack=0.01, release=0.35)

    for i in range(n):
        t = i / SAMPLE_RATE
        progress = i / n
        # Drop from 200Hz to 40Hz
        freq = 200 - 160 * progress ** 0.3
        s = math.sin(2 * math.pi * freq * t)
        # Add sub-harmonic
        s += math.sin(2 * math.pi * freq * 0.5 * t) * 0.5
        # Distortion for impact
        s = math.tanh(s * 1.5) * 0.8
        samples[i] = s * env[i] * volume

    return samples


def generate_tick(duration=0.08, volume=0.3):
    """Subtle tick — counting animation."""
    n = int(SAMPLE_RATE * duration)
    samples = [0.0] * n
    env = _envelope(n, attack=0.002, release=0.06)

    for i in range(n):
        t = i / SAMPLE_RATE
        s = math.sin(2 * math.pi * 2500 * t) * 0.6
        s += math.sin(2 * math.pi * 1200 * t) * 0.3
        samples[i] = s * env[i] * volume

    return samples


def init_sounds():
    """Generate all SFX and cache to disk. Skips if already exists."""
    os.makedirs(SOUNDS_DIR, exist_ok=True)

    sfx = {
        'whoosh': generate_whoosh,
        'ding': generate_ding,
        'pop': generate_pop,
        'swoosh': generate_swoosh,
        'bass_drop': generate_bass_drop,
        'tick': generate_tick,
    }

    generated = 0
    for name, gen_fn in sfx.items():
        filepath = os.path.join(SOUNDS_DIR, f"sfx_{name}.wav")
        if not os.path.exists(filepath):
            samples = gen_fn()
            _save_wav(samples, filepath)
            generated += 1
            print(f"  [OK] Generated: sfx_{name}.wav")
        else:
            pass  # Already cached

    if generated > 0:
        print(f"  SFX: {generated} new effects generated")
    return SOUNDS_DIR


def get_sfx_path(name):
    """Get path to a specific SFX. Returns None if not found."""
    filepath = os.path.join(SOUNDS_DIR, f"sfx_{name}.wav")
    if os.path.exists(filepath):
        return filepath
    # Try generating on-demand
    init_sounds()
    return filepath if os.path.exists(filepath) else None


if __name__ == "__main__":
    print("=== Sound Manager: Init SFX ===")
    init_sounds()
    print("=== SFX Ready ===")
