"""
tts_voiceover.py
Generate natural Indonesian female voiceover using Edge TTS.

Voice: id-ID-GadisNeural (Microsoft Neural TTS - Indonesian female)

Natural speech approach:
  - edge-tts uses rate + pitch params (NOT SSML — SSML is blocked by Microsoft)
  - Commas in text = natural pauses (TTS handles this automatically)
  - Short sentences with conversational Indonesian
  - Each scene gets voiceover for full coverage

Audio pipeline:
  TTS generates MP3 → video generator loads per scene →
  audio_normalizer normalizes RMS → set VOICEOVER_VOLUME=1.2 →
  CompositeAudioClip mixes with music (0.40) and SFX (0.35)
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

# Per-scene speaking style (rate + pitch via edge-tts native params)
# NOTE: edge-tts does NOT support SSML. Only rate/pitch/volume params work.
# Rates slightly POSITIVE = natural conversational pace, luwes, tidak lambat
SCENE_STYLES = {
    'hook':    {'rate': '+8%',  'pitch': '+3Hz'},    # Energetic, menarik perhatian
    'hero':    {'rate': '+3%',  'pitch': '+1Hz'},    # Normal, hangat
    'feature': {'rate': '+5%',  'pitch': '+1Hz'},    # Natural, informatif
    'proof':   {'rate': '+3%',  'pitch': '+0Hz'},    # Tenang tapi tetap natural
    'cta':     {'rate': '+8%',  'pitch': '+2Hz'},    # Energetic, mengajak
    'product': {'rate': '+5%',  'pitch': '+1Hz'},    # Normal
    'detail1': {'rate': '+5%',  'pitch': '+1Hz'},
    'detail2': {'rate': '+3%',  'pitch': '+1Hz'},
    'detail3': {'rate': '+5%',  'pitch': '+0Hz'},
}


# ═══════════════════════════════════════════════════════════════════
#  PRICE → INDONESIAN WORDS
# ═══════════════════════════════════════════════════════════════════

_SATUAN = ['', 'satu', 'dua', 'tiga', 'empat', 'lima', 'enam', 'tujuh', 'delapan', 'sembilan']
_BELASAN = ['sepuluh', 'sebelas', 'dua belas', 'tiga belas', 'empat belas', 'lima belas',
            'enam belas', 'tujuh belas', 'delapan belas', 'sembilan belas']

def _angka_ke_kata(n):
    """Convert integer 0-999999999 to Indonesian words."""
    if n == 0:
        return 'nol'
    if n < 0:
        return 'minus ' + _angka_ke_kata(-n)

    parts = []
    if n >= 1000000:
        juta = n // 1000000
        parts.append(_angka_ke_kata(juta) + ' juta')
        n %= 1000000
    if n >= 1000:
        ribu = n // 1000
        if ribu == 1:
            parts.append('seribu')
        else:
            parts.append(_angka_ke_kata(ribu) + ' ribu')
        n %= 1000
    if n >= 100:
        ratus = n // 100
        if ratus == 1:
            parts.append('seratus')
        else:
            parts.append(_satuan_kata(ratus) + ' ratus')
        n %= 100
    if n >= 20:
        puluh = n // 10
        parts.append(_satuan_kata(puluh) + ' puluh')
        n %= 10
    if n >= 10:
        parts.append(_BELASAN[n - 10])
        n = 0
    if n > 0:
        parts.append(_satuan_kata(n))

    return ' '.join(parts)

def _satuan_kata(n):
    return _SATUAN[n] if 0 <= n <= 9 else str(n)

def harga_ke_kata(harga_str):
    """Convert price string like 'Rp31.200' to 'tiga puluh satu ribu dua ratus rupiah'.
    
    Handles: Rp31.200 / Rp 31.200 / 31200 / Rp1.500.000
    """
    import re
    if not harga_str:
        return ''
    # Remove Rp prefix, spaces, dots (thousand separator), commas
    clean = re.sub(r'[Rr][Pp]\.?\s*', '', str(harga_str))
    clean = clean.replace('.', '').replace(',', '').strip()
    try:
        angka = int(clean)
    except ValueError:
        return ''
    if angka <= 0:
        return ''
    return _angka_ke_kata(angka) + ' rupiah'


# ═══════════════════════════════════════════════════════════════════
#  VOICEOVER SCRIPTS
#  Now includes product name, function, and price.
#  Written for natural spoken Indonesian.
#  Rules:
#    - Commas = TTS creates natural speech pauses
#    - Short, conversational sentences
#    - No foreign words (simpel→sederhana, spesial→istimewa)
#    - Price in full Indonesian words
# ═══════════════════════════════════════════════════════════════════

POOL_HOOK = [
    "Hai, kamu harus lihat yang satu ini.",
    "Eh, jangan dilewatkan ya.",
    "Ini dia, yang lagi banyak dicari orang.",
    "Hai, simak sampai selesai ya.",
    "Kamu pasti suka yang ini, coba deh lihat.",
]

POOL_FEATURE_TEMPLATE = [
    "Kualitasnya sudah terjamin ya, banyak yang sudah membuktikan.",
    "Bahannya bagus, tapi harganya masih terjangkau.",
    "Cocok untuk dipakai setiap hari, dan tahan lama juga.",
    "Desainnya sederhana, tapi tetap terlihat berkelas.",
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
    "Tertarik? Langsung saja cek di link ya.",
    "Ayo, langsung cek di link yang ada di bawah.",
    "Sebelum kehabisan, langsung saja cek ya.",
    "Link pembelian sudah tersedia di bawah.",
    "Jangan sampai kelewatan, langsung cek sekarang.",
]


def generate_voiceover_script(product_info, platform='yt_short'):
    """Generate voiceover scripts including product name, function, and price."""
    nama = product_info.get('nama', '')
    harga = product_info.get('harga', '')
    desc = product_info.get('deskripsi_singkat', '')
    
    # Convert price to Indonesian words
    harga_kata = harga_ke_kata(harga)
    
    # Hero text: mention product name
    if nama:
        hero_options = [
            f"Ini dia {nama}, yang lagi jadi favorit banyak orang.",
            f"{nama}, produk yang memang sudah terbukti bagus.",
            f"Kenalkan, {nama}, cocok banget untuk kamu.",
        ]
        hero_text = random.choice(hero_options)
    else:
        hero_text = "Produk yang satu ini, memang lagi jadi favorit banyak orang."
    
    # Feature text: mention function/description
    if desc:
        # Use first 60 chars of description
        short_desc = desc[:60].rstrip('.')
        feat_text = f"{short_desc}, cocok banget untuk kebutuhan kamu."
    else:
        feat_text = random.choice(POOL_FEATURE_TEMPLATE)
    
    # Price mention in proof scene
    if harga_kata:
        price_options = [
            f"Dengan harga hanya {harga_kata}, kualitasnya memang tidak mengecewakan.",
            f"Harganya cuma {harga_kata}, dan sudah banyak yang puas.",
            f"Cuma {harga_kata} saja, tapi kualitasnya luar biasa.",
        ]
        proof_text = random.choice(price_options)
    else:
        proof_text = random.choice(POOL_PROOF)

    if platform == 'yt_short':
        return {
            'hook': random.choice(POOL_HOOK),
            'hero': hero_text,
            'feature': feat_text,
            'proof': proof_text,
            'cta': random.choice(POOL_CTA),
        }
    elif platform == 'yt_long':
        return {
            'hook': random.choice(POOL_HOOK),
            'hero': hero_text,
            'detail1': feat_text,
            'detail2': proof_text,
            'detail3': random.choice(POOL_PROOF),
            'cta': random.choice(POOL_CTA),
        }
    elif platform == 'tt':
        return {
            'hook': random.choice(POOL_HOOK),
            'product': hero_text,
            'feature': feat_text,
            'cta': random.choice(POOL_CTA),
        }
    else:  # fb
        return {
            'hook': random.choice(POOL_HOOK),
            'product': hero_text,
            'feature': feat_text,
            'proof': proof_text,
            'cta': random.choice(POOL_CTA),
        }


# ═══════════════════════════════════════════════════════════════════
#  TTS ENGINE (edge-tts native params, NO SSML)
# ═══════════════════════════════════════════════════════════════════

async def _generate_tts_async(text, output_path, rate='-10%', pitch='+0Hz'):
    """Generate TTS audio using edge-tts native Communicate params.
    
    NOTE: edge-tts does NOT support custom SSML (blocked by Microsoft).
    Natural pauses come from commas and periods in the text itself.
    """
    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE_ID, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def generate_tts(text, output_path, scene_id='feature'):
    """Generate one TTS MP3 file.
    
    Returns True if generated successfully, False if failed.
    """
    try:
        style = SCENE_STYLES.get(scene_id, {'rate': '-10%', 'pitch': '+0Hz'})
        rate = style['rate']
        pitch = style['pitch']

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        asyncio.run(_generate_tts_async(text, output_path, rate, pitch))

        if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            print(f"    [TTS] OK: {os.path.basename(output_path)} ({scene_id})")
            return True
        else:
            print(f"    [TTS] Empty/small file: {os.path.basename(output_path)}")
            return False
    except Exception as e:
        print(f"    [TTS] Failed ({scene_id}): {e}")
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
