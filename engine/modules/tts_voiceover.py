"""
tts_voiceover.py
Generate natural Indonesian female voiceover using Edge TTS.

Voice: id-ID-GadisNeural (Microsoft Neural TTS — natural, with intonation)
Features:
  - Natural female voice, relaxed speaking pace
  - Price numbers converted to Indonesian words (31200 → "tiga puluh satu ribu dua ratus")
  - Per-scene voiceover scripts that COMPLEMENT (not duplicate) on-screen text
  - Multi-platform support: yt_short, yt_long, tt, fb

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
VOICE_ID = "id-ID-GadisNeural"   # Indonesian female neural voice
DEFAULT_RATE = "-5%"              # Slightly SLOWER for natural, relaxed feel
DEFAULT_PITCH = "+0Hz"            # Natural pitch
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers')

# Scene-specific speaking styles (relaxed, natural pace)
SCENE_STYLES = {
    'hook': {'rate': '+0%', 'pitch': '+1Hz'},     # Normal speed, slight excitement
    'hero': {'rate': '-5%', 'pitch': '+0Hz'},     # Calm, informative
    'feature': {'rate': '-3%', 'pitch': '+0Hz'},  # Steady, detailed
    'product': {'rate': '-3%', 'pitch': '+0Hz'},  # Descriptive
    'proof': {'rate': '-8%', 'pitch': '-1Hz'},    # Slower, trustworthy
    'cta': {'rate': '+0%', 'pitch': '+1Hz'},      # Normal, inviting (not pushy)
    'detail1': {'rate': '-5%', 'pitch': '+0Hz'},
    'detail2': {'rate': '-5%', 'pitch': '+0Hz'},
    'detail3': {'rate': '-5%', 'pitch': '+0Hz'},
}

# ═══════════════════════════════════════════════════════════════════
#  PRICE → INDONESIAN WORDS
# ═══════════════════════════════════════════════════════════════════

SATUAN = ['', 'satu', 'dua', 'tiga', 'empat', 'lima', 'enam', 'tujuh', 'delapan', 'sembilan']
BELASAN = ['sepuluh', 'sebelas', 'dua belas', 'tiga belas', 'empat belas', 'lima belas',
           'enam belas', 'tujuh belas', 'delapan belas', 'sembilan belas']

def _angka_ke_kata(n):
    """Convert integer to Indonesian words. E.g. 31200 → 'tiga puluh satu ribu dua ratus'"""
    if n == 0:
        return 'nol'
    if n < 0:
        return 'minus ' + _angka_ke_kata(-n)
    
    parts = []
    
    if n >= 1000000:
        juta = n // 1000000
        if juta == 1:
            parts.append('satu juta')
        else:
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
            parts.append(SATUAN[ratus] + ' ratus')
        n %= 100
    
    if n >= 20:
        puluh = n // 10
        parts.append(SATUAN[puluh] + ' puluh')
        n %= 10
    
    if 10 <= n <= 19:
        parts.append(BELASAN[n - 10])
        n = 0
    
    if n >= 1:
        parts.append(SATUAN[n])
    
    return ' '.join(parts)


def harga_ke_ucapan(harga_str):
    """Convert price string to natural Indonesian speech.
    
    Examples:
        'Rp31.200'  → 'tiga puluh satu ribu dua ratus rupiah'
        'Rp1.500.000' → 'satu juta lima ratus ribu rupiah'
        '65000' → 'enam puluh lima ribu rupiah'
    """
    if not harga_str:
        return ''
    
    # Remove Rp, Rp., dots, commas, spaces
    clean = re.sub(r'[Rr][Pp]\.?\s*', '', str(harga_str))
    clean = clean.replace('.', '').replace(',', '').replace(' ', '').strip()
    
    try:
        angka = int(clean)
        if angka <= 0:
            return ''
        kata = _angka_ke_kata(angka)
        return kata + ' rupiah'
    except ValueError:
        return ''


# ═══════════════════════════════════════════════════════════════════
#  VOICEOVER SCRIPT GENERATION
# ═══════════════════════════════════════════════════════════════════

def generate_voiceover_script(product_info, platform='yt_short'):
    """Generate voiceover script for each scene based on product info.
    
    Scripts COMPLEMENT on-screen text — they DON'T repeat the product name
    or hook text that's already visible. Instead they add context, emotion,
    and persuasion that text alone can't convey.
    
    Args:
        product_info: dict with nama, harga, deskripsi_singkat, hook, cta, category
        platform: yt_short, yt_long, tt, fb
    
    Returns:
        dict of {scene_id: voiceover_text}
    """
    nama = product_info.get('nama', 'Produk ini')
    harga = product_info.get('harga', '')
    desc = product_info.get('deskripsi_singkat', '')
    hook = product_info.get('hook', 'Cek produk ini!')
    cta = product_info.get('cta', 'Link ada di deskripsi!')
    rating = product_info.get('rating', 4.8)
    terjual = product_info.get('terjual', 1000)
    
    # Clean up
    nama_short = nama[:40].rstrip('.!?') if len(nama) > 40 else nama
    
    # Convert price to SPOKEN Indonesian
    harga_spoken = harga_ke_ucapan(harga)
    
    # Convert terjual to words
    terjual_spoken = _angka_ke_kata(int(terjual)) if terjual else 'banyak'
    
    # ── HOOK: attention grab (DON'T repeat hook text shown on screen) ──
    hook_scripts = [
        "Kamu wajib tau soal ini.",
        "Simak sampai habis ya, penting banget.",
        "Ini lagi banyak dicari orang.",
        "Jangan di-skip dulu, ini menarik banget.",
    ]
    
    # ── FEATURE: describe benefit (DON'T repeat product name shown on screen) ──
    if desc:
        feature_scripts = [
            f"Kualitasnya memang beda. {desc[:60]}",
            f"Yang bikin spesial, {desc[:60]}",
            f"Banyak yang suka karena {desc[:60]}",
        ]
    else:
        feature_scripts = [
            "Kualitasnya sudah terbukti. Banyak yang repeat order.",
            "Material premium dengan harga yang sangat terjangkau.",
            "Cocok banget buat kamu yang cari produk berkualitas.",
        ]
    
    # ── PROOF: social proof ──
    proof_scripts = [
        f"Rating {rating} bintang, sudah terjual {terjual_spoken} lebih.",
        f"Sudah dipercaya {terjual_spoken} lebih pembeli.",
        f"Bukan asal bilang bagus ya, buktinya sudah terjual {terjual_spoken} lebih.",
    ]
    
    # ── CTA: call to action (DON'T repeat CTA text shown on screen) ──
    cta_scripts = [
        "Tertarik? Langsung aja cek ya, stok terbatas.",
        "Buruan sebelum kehabisan. Link ada di bawah.",
        "Jangan sampai menyesal, langsung cek aja.",
    ]
    
    # ── PRICE: spoken price ──
    if harga_spoken:
        price_phrase = f"Harganya cuma {harga_spoken}."
    else:
        price_phrase = "Harganya sangat terjangkau."
    
    if platform == 'yt_short':
        return {
            'hook': random.choice(hook_scripts),
            'feature': random.choice(feature_scripts),
            'proof': f"{price_phrase} {random.choice(proof_scripts)}",
            'cta': random.choice(cta_scripts),
        }
    elif platform == 'yt_long':
        return {
            'hook': random.choice(hook_scripts),
            'detail1': random.choice(feature_scripts),
            'detail2': f"{price_phrase} Dengan harga segini, kualitasnya luar biasa.",
            'detail3': random.choice(proof_scripts),
            'cta': random.choice(cta_scripts),
        }
    elif platform == 'tt':
        return {
            'hook': random.choice(hook_scripts),
            'feature': random.choice(feature_scripts)[:80],
            'cta': f"{price_phrase} {random.choice(cta_scripts)}",
        }
    else:  # fb
        return {
            'hook': random.choice(hook_scripts),
            'feature': random.choice(feature_scripts),
            'proof': f"{price_phrase} {random.choice(proof_scripts)}",
            'cta': random.choice(cta_scripts),
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


def generate_tts(text, output_path, scene_id='hero'):
    """Generate TTS audio file (sync wrapper).
    
    Args:
        text: text to speak
        output_path: path to save MP3
        scene_id: scene type for style (hook, hero, feature, proof, cta)
    
    Returns:
        True if generated, False if failed
    """
    try:
        style = SCENE_STYLES.get(scene_id, {})
        rate = style.get('rate', DEFAULT_RATE)
        pitch = style.get('pitch', DEFAULT_PITCH)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        asyncio.run(_generate_tts_async(text, output_path, rate, pitch))
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            print(f"    [TTS] Generated: {os.path.basename(output_path)} ({scene_id})")
            return True
        return False
    except Exception as e:
        print(f"    [TTS] Failed: {e}")
        return False


def generate_voiceover_for_product(product_info, produk_id, platform='yt_short', output_dir=None):
    """Generate all voiceover files for a product.
    
    Creates one MP3 per scene, stored in:
      engine/data/voiceovers/{produk_id}/{platform}/
    
    Args:
        product_info: dict with product details
        produk_id: product ID
        platform: yt_short, yt_long, tt, fb
        output_dir: override output directory
    
    Returns:
        dict of {scene_id: mp3_path} for successfully generated files
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR
    
    vo_dir = os.path.join(output_dir, produk_id, platform)
    os.makedirs(vo_dir, exist_ok=True)
    
    # ALWAYS regenerate (don't cache — scripts have random variety)
    # Clean old files
    for f in os.listdir(vo_dir):
        if f.startswith('vo_') and f.endswith('.mp3'):
            os.remove(os.path.join(vo_dir, f))
    
    # Generate scripts
    scripts = generate_voiceover_script(product_info, platform)
    
    result = {}
    print(f"  [TTS] Generating {platform} voiceovers for {produk_id}...")
    
    for scene_id, text in scripts.items():
        if not text or len(text.strip()) < 5:
            continue
        
        mp3_path = os.path.join(vo_dir, f"vo_{scene_id}.mp3")
        
        if generate_tts(text, mp3_path, scene_id):
            result[scene_id] = mp3_path
    
    print(f"  [TTS] Done: {len(result)}/{len(scripts)} scenes")
    return result


def generate_all_voiceovers(queue_file, platforms=None):
    """Generate voiceovers for all products in a queue file.
    
    Args:
        queue_file: path to JSONL queue file
        platforms: list of platforms, default ALL ['yt_short', 'yt_long', 'tt', 'fb']
    """
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
    
    print(f"[TTS] Generating voiceovers for {len(jobs)} products × {len(platforms)} platforms...")
    
    for job in jobs:
        produk_id = job.get('produk_id', '')
        for platform in platforms:
            generate_voiceover_for_product(job, produk_id, platform)
    
    print(f"[TTS] All done — {len(jobs)} products × {len(platforms)} platforms")


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
