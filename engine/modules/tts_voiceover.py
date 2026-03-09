"""
tts_voiceover.py
Generate natural Indonesian female voiceover using Edge TTS.

Voice: id-ID-GadisNeural (Microsoft Neural TTS — natural, with intonation)
Features:
  - Natural female voice with proper Indonesian intonation
  - Prosody control: rate, pitch for emphasis
  - Smart pauses between sentences
  - Per-scene voiceover scripts generated from product info
  
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
VOICE_ID = "id-ID-GadisNeural"   # Indonesian female neural voice
DEFAULT_RATE = "+5%"              # Slightly faster for engaging content
DEFAULT_PITCH = "+0Hz"            # Natural pitch
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers')

# Scene-specific speaking styles
SCENE_STYLES = {
    'hook': {'rate': '+10%', 'pitch': '+2Hz'},    # Energetic, attention-grabbing
    'hero': {'rate': '+0%', 'pitch': '+0Hz'},     # Clear, informative
    'feature': {'rate': '+0%', 'pitch': '+0Hz'},  # Steady, detailed
    'product': {'rate': '+0%', 'pitch': '+0Hz'},  # Descriptive
    'proof': {'rate': '-5%', 'pitch': '-1Hz'},    # Calm, trustworthy
    'cta': {'rate': '+8%', 'pitch': '+2Hz'},      # Urgent, exciting
    'detail1': {'rate': '+0%', 'pitch': '+0Hz'},
    'detail2': {'rate': '+0%', 'pitch': '+0Hz'},
    'detail3': {'rate': '+0%', 'pitch': '+0Hz'},
}

# ═══════════════════════════════════════════════════════════════════
#  VOICEOVER SCRIPT GENERATION
# ═══════════════════════════════════════════════════════════════════

def generate_voiceover_script(product_info, platform='yt_short'):
    """Generate voiceover script for each scene based on product info.
    
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
    
    # Clean up text for natural speech
    nama_short = nama[:50].rstrip('.!?') if len(nama) > 50 else nama
    
    # Price formatting for speech
    harga_speak = harga.replace('Rp', 'Rupiah ').replace('.', ' ') if harga else ''
    
    # Randomize phrasing for variety
    hook_intros = [
        f"Hei, {hook}",
        f"Kamu harus tau ini. {hook}",
        f"Stop dulu! {hook}",
        f"Wajib simak sampai habis. {hook}",
    ]
    
    feature_phrases = [
        f"Ini dia {nama_short}. {desc[:80] if desc else 'Produk kualitas terbaik di kelasnya.'}",
        f"{nama_short} ini punya banyak keunggulan. {desc[:80] if desc else 'Kualitas premium dengan harga terjangkau.'}",
        f"Kenapa harus pilih {nama_short}? {desc[:80] if desc else 'Karena kualitasnya sudah terbukti.'}",
    ]
    
    proof_phrases = [
        f"Rating {rating} bintang, dan sudah terjual lebih dari {terjual} buah.",
        f"Sudah dipercaya {terjual} lebih pembeli, dengan rating {rating} bintang.",
        f"Bukan cuma kualitas, buktinya {terjual} lebih orang sudah beli. Rating {rating} bintang.",
    ]
    
    cta_phrases = [
        f"Gimana, tertarik? {cta} Jangan sampai kehabisan ya!",
        f"Buruan, stok terbatas! {cta}",
        f"{cta} Harga segini gak akan lama!",
    ]
    
    if platform == 'yt_short':
        return {
            'hook': random.choice(hook_intros),
            'hero': f"{nama_short}. {'Harganya cuma ' + harga_speak + '.' if harga_speak else 'Harga sangat terjangkau.'}",
            'feature': random.choice(feature_phrases),
            'proof': random.choice(proof_phrases),
            'cta': random.choice(cta_phrases),
        }
    elif platform == 'yt_long':
        return {
            'hook': random.choice(hook_intros),
            'hero': f"Hari ini kita bahas {nama_short}. {'Dengan harga ' + harga_speak + ', ' if harga_speak else ''}produk ini lagi banyak dicari.",
            'detail1': random.choice(feature_phrases),
            'detail2': f"Yang bikin spesial, kualitasnya memang beda dari yang lain. Cocok banget buat kamu yang cari produk berkualitas.",
            'detail3': random.choice(proof_phrases),
            'cta': random.choice(cta_phrases),
        }
    elif platform == 'tt':
        return {
            'hook': random.choice(hook_intros),
            'product': f"{nama_short}. {'Cuma ' + harga_speak + '!' if harga_speak else 'Harga super terjangkau!'}",
            'feature': random.choice(feature_phrases)[:100],
            'cta': random.choice(cta_phrases),
        }
    else:  # fb
        return {
            'hook': random.choice(hook_intros),
            'product': f"Ini dia, {nama_short}. {'Harga ' + harga_speak + '.' if harga_speak else ''}",
            'feature': random.choice(feature_phrases),
            'proof': random.choice(proof_phrases),
            'cta': random.choice(cta_phrases),
        }


# ═══════════════════════════════════════════════════════════════════
#  TTS ENGINE
# ═══════════════════════════════════════════════════════════════════

async def _generate_tts_async(text, output_path, rate=None, pitch=None):
    """Generate TTS audio file using edge-tts."""
    import edge_tts
    
    rate = rate or DEFAULT_RATE
    pitch = pitch or DEFAULT_PITCH
    
    # Add natural pauses at punctuation
    text = text.replace('. ', '... ')  # Longer pause at periods
    text = text.replace('! ', '!.. ')  # Pause after exclamation
    text = text.replace('? ', '?.. ')  # Pause after question
    text = text.replace(', ', ',. ')   # Short pause at commas
    
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
    
    # Generate scripts
    scripts = generate_voiceover_script(product_info, platform)
    
    result = {}
    print(f"  [TTS] Generating {platform} voiceovers for {produk_id}...")
    
    for scene_id, text in scripts.items():
        if not text or len(text.strip()) < 5:
            continue
        
        mp3_path = os.path.join(vo_dir, f"vo_{scene_id}.mp3")
        
        # Skip if already generated (cache)
        if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 1000:
            result[scene_id] = mp3_path
            continue
        
        if generate_tts(text, mp3_path, scene_id):
            result[scene_id] = mp3_path
    
    print(f"  [TTS] Done: {len(result)}/{len(scripts)} scenes")
    return result


def generate_all_voiceovers(queue_file, platform='yt_short'):
    """Generate voiceovers for all products in a queue file.
    
    Args:
        queue_file: path to JSONL queue file
        platform: yt_short, yt_long, tt, fb
    """
    if not os.path.exists(queue_file):
        print(f"  [TTS] Queue not found: {queue_file}")
        return
    
    jobs = []
    with open(queue_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                jobs.append(json.loads(line.strip()))
    
    print(f"[TTS] Generating voiceovers for {len(jobs)} products ({platform})...")
    
    for job in jobs:
        produk_id = job.get('produk_id', '')
        generate_voiceover_for_product(job, produk_id, platform)
    
    print(f"[TTS] All done — {len(jobs)} products")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue', default='engine/queue/storyboard_queue.jsonl')
    parser.add_argument('--platform', default='yt_short', 
                       choices=['yt_short', 'yt_long', 'tt', 'fb'])
    args = parser.parse_args()
    
    generate_all_voiceovers(args.queue, args.platform)
