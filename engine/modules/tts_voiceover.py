"""
tts_voiceover.py
Generate natural Indonesian female voiceover using Edge TTS.

Voice: id-ID-GadisNeural (Microsoft Neural TTS)
Design:
  - Voiceover covers EVERY scene of the video (professional ads style)
  - NEVER says product name or price (both already shown as text)
  - Uses simple Indonesian that TTS pronounces clearly
  - Rate -8% for relaxed, natural speaking pace

Used by: all video generators (YT Short, YT Long, TT, FB)
"""

import os
import sys
import json
import asyncio
import random

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
VOICE_ID = "id-ID-GadisNeural"
DEFAULT_RATE = "-8%"
DEFAULT_PITCH = "+0Hz"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers')

SCENE_STYLES = {
    'hook':    {'rate': '-3%',  'pitch': '+0Hz'},
    'hero':    {'rate': '-8%',  'pitch': '+0Hz'},
    'feature': {'rate': '-8%',  'pitch': '+0Hz'},
    'proof':   {'rate': '-10%', 'pitch': '+0Hz'},
    'cta':     {'rate': '-5%',  'pitch': '+0Hz'},
    'detail1': {'rate': '-8%',  'pitch': '+0Hz'},
    'detail2': {'rate': '-8%',  'pitch': '+0Hz'},
    'detail3': {'rate': '-8%',  'pitch': '+0Hz'},
    'product': {'rate': '-8%',  'pitch': '+0Hz'},
}


# ═══════════════════════════════════════════════════════════════════
#  SCRIPT POOLS (pre-written for clear TTS pronunciation)
#  Rule: NEVER mention product name or price
# ═══════════════════════════════════════════════════════════════════

POOL_HOOK = [
    "Kamu harus lihat ini.",
    "Jangan lewatkan yang satu ini ya.",
    "Ini lagi banyak dicari orang.",
    "Simak sampai akhir ya.",
    "Mau tau produk yang lagi viral?",
]

POOL_HERO = [
    "Produk ini sudah banyak yang cari.",
    "Kualitas terjamin dan harga masih terjangkau.",
    "Liat sendiri ya betapa kerennya.",
    "Yang satu ini memang layak untuk dimiliki.",
    "Ini dia yang sedang jadi favorit banyak orang.",
]

POOL_FEATURE = [
    "Kualitasnya memang oke. Banyak yang sudah buktikan sendiri.",
    "Bahan premium dan tahan lama.",
    "Cocok untuk pemakaian sehari hari.",
    "Desainnya simpel tapi tetap terlihat berkelas.",
    "Fiturnya lengkap dan mudah digunakan.",
]

POOL_PROOF = [
    "Ratingnya tinggi dan sudah banyak yang beli.",
    "Banyak pembeli yang kasih ulasan positif.",
    "Sudah terbukti memuaskan.",
    "Ulasan dari pembeli selalu bagus.",
    "Banyak yang sudah order ulang.",
]

POOL_CTA = [
    "Tertarik? Cek linknya ya.",
    "Langsung saja cek di link di bawah.",
    "Sebelum kehabisan, cek dulu ya.",
    "Link pembelian ada di deskripsi.",
    "Jangan sampai menyesal, langsung cek.",
]


def generate_voiceover_script(product_info, platform='yt_short'):
    """Generate voiceover script for EVERY scene.
    
    Each scene gets a voiceover line so the narration
    covers the entire video duration (professional style).
    """
    if platform == 'yt_short':
        # 5 scenes: hook(0-3), hero(3-12), feature(12-30), proof(30-40), cta(40-45)
        return {
            'hook': random.choice(POOL_HOOK),
            'hero': random.choice(POOL_HERO),
            'feature': random.choice(POOL_FEATURE),
            'proof': random.choice(POOL_PROOF),
            'cta': random.choice(POOL_CTA),
        }
    elif platform == 'yt_long':
        return {
            'hook': random.choice(POOL_HOOK),
            'hero': random.choice(POOL_HERO),
            'detail1': random.choice(POOL_FEATURE),
            'detail2': "Yang bikin spesial, kualitasnya memang beda dari yang lain.",
            'detail3': random.choice(POOL_PROOF),
            'cta': random.choice(POOL_CTA),
        }
    elif platform == 'tt':
        # TikTok shorter: 4 scenes
        return {
            'hook': random.choice(POOL_HOOK),
            'product': random.choice(POOL_HERO),
            'feature': random.choice(POOL_FEATURE),
            'cta': random.choice(POOL_CTA),
        }
    else:  # fb
        return {
            'hook': random.choice(POOL_HOOK),
            'product': random.choice(POOL_HERO),
            'feature': random.choice(POOL_FEATURE),
            'proof': random.choice(POOL_PROOF),
            'cta': random.choice(POOL_CTA),
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
    """Generate voiceover MP3s for a product (one per scene)."""
    if output_dir is None:
        output_dir = OUTPUT_DIR
    vo_dir = os.path.join(output_dir, produk_id, platform)
    os.makedirs(vo_dir, exist_ok=True)

    # Clean old files
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
