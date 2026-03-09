"""
tts_voiceover.py
Generate natural Indonesian female voiceover using Edge TTS + SSML.

Voice: id-ID-GadisNeural (Microsoft Neural TTS - Indonesian female)

SSML-powered natural speech:
  - <break> tags for natural pauses between phrases
  - <prosody> for varied pace (slower on key points, normal elsewhere)
  - Conversational Indonesian with natural sentence flow
  - Each scene gets voiceover for full coverage

Audio pipeline:
  TTS generates MP3 → video generator loads per scene →
  audio_normalizer normalizes RMS → set VOICEOVER_VOLUME=1.0 →
  CompositeAudioClip mixes with music (0.55) and SFX (0.45)
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
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers')


# ═══════════════════════════════════════════════════════════════════
#  SSML BUILDER
#  Wraps text in SSML tags for natural prosody and pauses
# ═══════════════════════════════════════════════════════════════════

def _build_ssml(text, rate="-10%", pitch="+0Hz"):
    """Wrap text in SSML with prosody settings.
    
    Automatically adds <break> tags at commas and periods for
    natural pauses. Wraps everything in <speak> and <voice>.
    """
    # Add natural pauses: replace punctuation with breaks
    ssml_text = text
    ssml_text = ssml_text.replace('. ', '. <break time="400ms"/> ')
    ssml_text = ssml_text.replace(', ', ', <break time="200ms"/> ')
    ssml_text = ssml_text.replace('! ', '! <break time="350ms"/> ')
    ssml_text = ssml_text.replace('? ', '? <break time="350ms"/> ')
    
    ssml = (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="id-ID">'
        f'<voice name="{VOICE_ID}">'
        f'<prosody rate="{rate}" pitch="{pitch}">'
        f'{ssml_text}'
        f'</prosody>'
        f'</voice>'
        f'</speak>'
    )
    return ssml


# Per-scene SSML settings (rate + pitch)
SCENE_SSML = {
    'hook':    {'rate': '-5%',  'pitch': '+2Hz'},    # Slightly upbeat, attention-grab
    'hero':    {'rate': '-12%', 'pitch': '+0Hz'},    # Slow, warm, inviting
    'feature': {'rate': '-10%', 'pitch': '+0Hz'},    # Steady, informative
    'proof':   {'rate': '-15%', 'pitch': '-1Hz'},    # Slower, deeper = trustworthy
    'cta':     {'rate': '-8%',  'pitch': '+1Hz'},    # Slightly upbeat, encouraging
    'product': {'rate': '-12%', 'pitch': '+0Hz'},    # Warm
    'detail1': {'rate': '-10%', 'pitch': '+0Hz'},
    'detail2': {'rate': '-12%', 'pitch': '+0Hz'},
    'detail3': {'rate': '-10%', 'pitch': '+0Hz'},
}


# ═══════════════════════════════════════════════════════════════════
#  VOICEOVER SCRIPT POOLS
#  Written for natural Indonesian spoken flow.
#  Rules:
#    - NEVER mention product name or price (shown on screen)
#    - Use conversational, everyday Indonesian
#    - Sentences end naturally (tidak dipotong)
#    - Avoid foreign/English words TTS might mispronounce
#    - Short phrases with natural pauses
# ═══════════════════════════════════════════════════════════════════

POOL_HOOK = [
    "Hai, kamu harus lihat yang satu ini.",
    "Eh, jangan di lewatkan ya.",
    "Ini dia, yang lagi banyak dicari orang.",
    "Hai, simak sampai selesai ya.",
    "Kamu pasti suka yang ini, coba deh lihat.",
]

POOL_HERO = [
    "Produk yang satu ini, memang lagi jadi favorit banyak orang.",
    "Yang lagi viral, dan memang bagus kualitasnya.",
    "Ini yang banyak orang cari, dan ternyata memang oke.",
    "Satu produk yang patut kamu pertimbangkan.",
    "Kualitas dan harganya, pas di kantong.",
]

POOL_FEATURE = [
    "Kualitasnya sudah terjamin ya, banyak yang sudah membuktikan.",
    "Bahannya premium, tapi harganya masih terjangkau.",
    "Cocok untuk dipakai setiap hari, dan tahan lama juga.",
    "Desainnya simpel, tapi tetap terlihat berkelas.",
    "Fiturnya lengkap, dan mudah digunakan siapa saja.",
]

POOL_PROOF = [
    "Ratingnya tinggi, dan sudah banyak sekali yang membeli.",
    "Banyak pembeli yang memberikan ulasan positif.",
    "Sudah terbukti ya, bukan sekedar klaim saja.",
    "Ulasan dari para pembeli, memang sangat memuaskan.",
    "Banyak yang membeli lagi, karena memang puas.",
]

POOL_CTA = [
    "Tertarik? langsung saja cek di link ya.",
    "Ayo, langsung cek di link yang ada di bawah.",
    "Sebelum kehabisan, langsung saja cek ya.",
    "Link pembelian sudah tersedia di bawah.",
    "Jangan sampai kelewatan, langsung cek sekarang.",
]


def generate_voiceover_script(product_info, platform='yt_short'):
    """Generate voiceover scripts for every scene of the video.
    
    Each script is a natural conversational sentence that
    COMPLEMENTS on-screen text (never duplicates it).
    """
    if platform == 'yt_short':
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
            'detail2': "Yang membuat produk ini spesial, adalah kualitasnya yang memang beda.",
            'detail3': random.choice(POOL_PROOF),
            'cta': random.choice(POOL_CTA),
        }
    elif platform == 'tt':
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
#  TTS ENGINE (SSML-powered)
# ═══════════════════════════════════════════════════════════════════

async def _generate_tts_async(ssml_text, output_path):
    """Generate TTS audio from SSML string using edge-tts."""
    import edge_tts
    communicate = edge_tts.Communicate(ssml_text, VOICE_ID)
    await communicate.save(output_path)


def generate_tts(text, output_path, scene_id='feature'):
    """Generate one TTS MP3 file with SSML prosody.
    
    Args:
        text: plain text to speak
        output_path: where to save MP3
        scene_id: scene type for prosody settings
    
    Returns:
        True if generated, False if failed
    """
    try:
        style = SCENE_SSML.get(scene_id, {'rate': '-10%', 'pitch': '+0Hz'})
        ssml = _build_ssml(text, rate=style['rate'], pitch=style['pitch'])
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        asyncio.run(_generate_tts_async(ssml, output_path))
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            print(f"    [TTS] OK: {os.path.basename(output_path)} ({scene_id})")
            return True
        return False
    except Exception as e:
        print(f"    [TTS] SSML failed ({scene_id}): {e}")
        # Fallback: try plain text without SSML
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, VOICE_ID, 
                                                rate=style['rate'], 
                                                pitch=style['pitch'])
            asyncio.run(communicate.save(output_path))
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                print(f"    [TTS] OK (fallback): {os.path.basename(output_path)}")
                return True
        except Exception as e2:
            print(f"    [TTS] Fallback also failed: {e2}")
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

    print(f"[TTS SSML] {len(jobs)} products x {len(platforms)} platforms...")
    for job in jobs:
        produk_id = job.get('produk_id', '')
        for platform in platforms:
            generate_voiceover_for_product(job, produk_id, platform)
    print(f"[TTS SSML] All done")


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
