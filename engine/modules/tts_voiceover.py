"""
tts_voiceover.py
Generate natural Indonesian female voiceover using Edge TTS.

Voice: id-ID-GadisNeural (Microsoft Neural TTS)
Design principles:
  - Voiceover ONLY says what is NOT shown on screen
  - NO product name (already shown as text)
  - NO price (already shown as text)
  - Simple, short sentences with easy-to-pronounce words
  - Relaxed, conversational tone

Used by: all video generators (YT Short, YT Long, TT, FB)
"""

import os
import sys
import json
import asyncio
import random
import re

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
VOICE_ID = "id-ID-GadisNeural"
DEFAULT_RATE = "-8%"              # Slow, relaxed, natural
DEFAULT_PITCH = "+0Hz"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers')

# Relaxed scene styles
SCENE_STYLES = {
    'hook':    {'rate': '-3%', 'pitch': '+0Hz'},
    'feature': {'rate': '-8%', 'pitch': '+0Hz'},
    'proof':   {'rate': '-10%', 'pitch': '+0Hz'},
    'cta':     {'rate': '-5%', 'pitch': '+0Hz'},
    'detail1': {'rate': '-8%', 'pitch': '+0Hz'},
    'detail2': {'rate': '-8%', 'pitch': '+0Hz'},
    'detail3': {'rate': '-8%', 'pitch': '+0Hz'},
}


# ═══════════════════════════════════════════════════════════════════
#  VOICEOVER SCRIPTS
#  Rule: NEVER mention product name or price (already on screen)
#  Rule: Use simple words TTS can pronounce clearly
# ═══════════════════════════════════════════════════════════════════

# Simple hook lines (no product name, no complex words)
HOOK_LINES = [
    "Kamu harus liat ini.",
    "Jangan lewatkan yang satu ini ya.",
    "Ini lagi banyak dicari orang.",
    "Simak sampai akhir ya.",
    "Cocok untuk kamu yang lagi cari solusi.",
]

# Feature descriptions (generic, no product name)
FEATURE_LINES = [
    "Kualitasnya memang oke. Banyak yang sudah buktikan sendiri.",
    "Bahan premium dengan harga yang masih masuk akal.",
    "Cocok untuk pemakaian sehari hari. Tahan lama juga.",
    "Desainnya simpel tapi tetap terlihat berkelas.",
    "Produk ini memang beda dari yang lain. Layak dicoba.",
]

# Social proof (no price, no exact numbers)
PROOF_LINES = [
    "Ratingnya tinggi, dan sudah banyak yang beli.",
    "Banyak pembeli yang kasih ulasan positif.",
    "Sudah terbukti ya, bukan asal klaim.",
    "Ulasan dari pembeli memang memuaskan.",
    "Banyak yang sudah order ulang.",
]

# CTA (simple, no price)
CTA_LINES = [
    "Tertarik? Cek linknya ya.",
    "Langsung aja cek di link.",
    "Sebelum kehabisan, cek dulu ya.",
    "Link pembelian ada di bawah.",
    "Jangan sampai menyesal ya, langsung cek.",
]


def generate_voiceover_script(product_info, platform='yt_short'):
    """Generate voiceover scripts per scene.
    
    NEVER includes: product name, price, or complex words.
    Only includes: emotion, persuasion, context that complements text.
    """
    if platform == 'yt_short':
        return {
            'hook': random.choice(HOOK_LINES),
            'feature': random.choice(FEATURE_LINES),
            'cta': random.choice(CTA_LINES),
        }
    elif platform == 'yt_long':
        return {
            'hook': random.choice(HOOK_LINES),
            'detail1': random.choice(FEATURE_LINES),
            'detail3': random.choice(PROOF_LINES),
            'cta': random.choice(CTA_LINES),
        }
    elif platform == 'tt':
        return {
            'hook': random.choice(HOOK_LINES),
            'cta': random.choice(CTA_LINES),
        }
    else:  # fb
        return {
            'hook': random.choice(HOOK_LINES),
            'feature': random.choice(FEATURE_LINES),
            'cta': random.choice(CTA_LINES),
        }


# ═══════════════════════════════════════════════════════════════════
#  TTS ENGINE
# ═══════════════════════════════════════════════════════════════════

async def _generate_tts_async(text, output_path, rate=None, pitch=None):
    """Generate TTS audio file using edge-tts."""
    import edge_tts

    rate = rate or DEFAULT_RATE
    pitch = pitch or DEFAULT_PITCH

    communicate = edge_tts.Communicate(text, VOICE_ID, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def generate_tts(text, output_path, scene_id='feature'):
    """Generate TTS audio file (sync wrapper)."""
    try:
        style = SCENE_STYLES.get(scene_id, {})
        rate = style.get('rate', DEFAULT_RATE)
        pitch = style.get('pitch', DEFAULT_PITCH)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        asyncio.run(_generate_tts_async(text, output_path, rate, pitch))

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            print(f"    [TTS] OK: {os.path.basename(output_path)} ({scene_id})")
            return True
        return False
    except Exception as e:
        print(f"    [TTS] Failed: {e}")
        return False


def generate_voiceover_for_product(product_info, produk_id, platform='yt_short', output_dir=None):
    """Generate voiceover MP3s for a product."""
    if output_dir is None:
        output_dir = OUTPUT_DIR

    vo_dir = os.path.join(output_dir, produk_id, platform)
    os.makedirs(vo_dir, exist_ok=True)

    # Clean old files (always regenerate for variety)
    for f in os.listdir(vo_dir):
        if f.startswith('vo_') and f.endswith('.mp3'):
            try:
                os.remove(os.path.join(vo_dir, f))
            except Exception:
                pass

    scripts = generate_voiceover_script(product_info, platform)

    result = {}
    print(f"  [TTS] {platform} for {produk_id}...")

    for scene_id, text in scripts.items():
        if not text or len(text.strip()) < 5:
            continue

        mp3_path = os.path.join(vo_dir, f"vo_{scene_id}.mp3")
        if generate_tts(text, mp3_path, scene_id):
            result[scene_id] = mp3_path

    print(f"  [TTS] Done: {len(result)}/{len(scripts)} scenes")
    return result


def generate_all_voiceovers(queue_file, platforms=None):
    """Generate voiceovers for all products across all platforms."""
    if not os.path.exists(queue_file):
        print(f"  [TTS] Queue not found: {queue_file}")
        return

    if platforms is None:
        platforms = ['yt_short', 'yt_long', 'tt', 'fb']

    jobs = []
    with open(queue_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                jobs.append(json.loads(line.strip()))

    print(f"[TTS] {len(jobs)} products x {len(platforms)} platforms...")

    for job in jobs:
        produk_id = job.get('produk_id', '')
        for platform in platforms:
            generate_voiceover_for_product(job, produk_id, platform)

    print(f"[TTS] All done")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue', default='engine/queue/storyboard_queue.jsonl')
    parser.add_argument('--platform', default='all',
                       choices=['all', 'yt_short', 'yt_long', 'tt', 'fb'])
    args = parser.parse_args()

    if args.platform == 'all':
        generate_all_voiceovers(args.queue)
    else:
        generate_all_voiceovers(args.queue, [args.platform])
