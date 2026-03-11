"""
tts_voiceover.py
Generate natural Indonesian voiceover using Edge TTS.

Per-account voice:
  yt_1 (fashion):   GadisNeural (female, high pitch)
  yt_2 (gadget):    ArdiNeural  (male, neutral pitch)
  yt_3 (beauty):    GadisNeural (female, warm pitch)
  yt_4 (home):      ArdiNeural  (male, low pitch)
  yt_5 (wellness):  GadisNeural (female, calm pitch)
  tt_1, fb_1:       GadisNeural (female, default)

Natural speech approach:
  - edge-tts uses rate + pitch params (NOT SSML)
  - Commas in text = natural pauses
  - Short sentences with conversational Indonesian

Audio pipeline:
  TTS generates MP3 -> video generator loads per scene ->
  audio_normalizer normalizes RMS -> VOICEOVER_VOLUME=0.75 ->
  CompositeAudioClip mixes with music (0.30) and SFX (0.30)
"""

import os
import sys
import json
import asyncio
import random

# ====================================================================
#  CONFIG
# ====================================================================
DEFAULT_VOICE = "id-ID-GadisNeural"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers')

# Per-account voice: each channel gets a DISTINCT voice
ACCOUNT_VOICES = {
    'yt_1': {'voice': 'id-ID-GadisNeural', 'pitch_offset': '+2Hz'},   # fashion: female high
    'yt_2': {'voice': 'id-ID-ArdiNeural',  'pitch_offset': '+2Hz'},   # gadget: male (boosted pitch for clarity)
    'yt_3': {'voice': 'id-ID-GadisNeural', 'pitch_offset': '+0Hz'},   # beauty: female warm
    'yt_4': {'voice': 'id-ID-ArdiNeural',  'pitch_offset': '+1Hz'},   # home: male (boosted pitch for clarity)
    'yt_5': {'voice': 'id-ID-GadisNeural', 'pitch_offset': '-1Hz'},   # wellness: female calm
    'tt_1': {'voice': 'id-ID-GadisNeural', 'pitch_offset': '+1Hz'},   # tiktok
    'fb_1': {'voice': 'id-ID-ArdiNeural',  'pitch_offset': '+2Hz'},   # facebook: male (boosted)
}

# Per-scene speaking style (rate + pitch via edge-tts native params)
# NOTE: edge-tts does NOT support SSML. Only rate/pitch/volume params work.
# Rates POSITIVE = cepat natural, luwes, tidak lambat
SCENE_STYLES = {
    'hook':    {'rate': '+15%', 'pitch': '+3Hz'},    # Cepat, menarik perhatian
    'hero':    {'rate': '+10%', 'pitch': '+1Hz'},    # Natural cepat
    'feature': {'rate': '+12%', 'pitch': '+1Hz'},    # Informatif cepat
    'proof':   {'rate': '+10%', 'pitch': '+0Hz'},    # Tenang tapi cepat
    'cta':     {'rate': '+15%', 'pitch': '+2Hz'},    # Energetic, cepat
    'product': {'rate': '+12%', 'pitch': '+1Hz'},    # Normal cepat
    'detail1': {'rate': '+12%', 'pitch': '+1Hz'},
    'detail2': {'rate': '+10%', 'pitch': '+1Hz'},
    'detail3': {'rate': '+12%', 'pitch': '+0Hz'},
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

# ═══════════════════════════════════════════════════════════════════
#  PER-CATEGORY VOICEOVER POOLS
#  Each YT account has a DIFFERENT category → DIFFERENT themed scripts.
#  No duplicate phrases across scenes in the same video.
# ═══════════════════════════════════════════════════════════════════

CATEGORY_HOOKS = {
    'fashion': [
        "Hai, cek gaya terbaru yang satu ini.",
        "Mau tampil beda? Simak sampai habis ya.",
        "Ini dia item fashion yang lagi banyak dicari.",
        "Buat kamu yang suka tampil keren, wajib lihat.",
        "Pengen upgrade penampilan? Lihat dulu yang ini.",
    ],
    'gadget': [
        "Hai, ada gadget menarik yang perlu kamu tahu.",
        "Buat kamu yang suka teknologi, ini wajib cek.",
        "Gadget yang satu ini lagi banyak dibicarakan.",
        "Mau setup makin keren? Simak dulu ya.",
        "Ini dia perangkat yang lagi trending.",
    ],
    'beauty': [
        "Hai, ada produk perawatan yang wajib kamu coba.",
        "Mau kulit makin sehat? Simak yang satu ini.",
        "Produk kecantikan yang lagi banyak dicari orang.",
        "Buat kamu yang suka merawat diri, wajib lihat.",
        "Pengen tampil segar setiap hari? Cek ini dulu.",
    ],
    'home': [
        "Hai, ada solusi rumah tangga yang praktis.",
        "Mau rumah makin rapi? Lihat yang satu ini.",
        "Alat rumah tangga yang memang berguna.",
        "Buat kamu yang suka rumah bersih dan tertata.",
        "Ini dia peralatan rumah yang lagi diminati.",
    ],
    'wellness': [
        "Hai, ada produk kesehatan yang perlu kamu tahu.",
        "Mau hidup lebih sehat? Simak sampai habis.",
        "Produk kebugaran yang lagi banyak diminati.",
        "Buat kamu yang peduli kesehatan, wajib cek.",
        "Ini dia alat olahraga yang lagi naik daun.",
    ],
}

CATEGORY_FEATURES = {
    'fashion': [
        "Kualitasnya bagus dan tahan lama.",
        "Desainnya kekinian, bisa dipadupadankan.",
        "Tersedia banyak pilihan warna dan ukuran.",
        "Praktis digunakan untuk berbagai kesempatan.",
        "Tampilannya elegan dan tetap nyaman.",
    ],
    'gadget': [
        "Performanya stabil dan baterainya tahan lama.",
        "Mudah digunakan dan hasilnya memuaskan.",
        "Koneksinya cepat dan tidak mudah putus.",
        "Desainnya ringkas dan tidak makan tempat.",
        "Fiturnya lengkap untuk harga di kelasnya.",
    ],
    'beauty': [
        "Teksturnya ringan dan cepat meresap di kulit.",
        "Hasilnya terasa dari pemakaian pertama.",
        "Aman untuk kulit sensitif dan sudah teruji.",
        "Aromanya lembut dan tidak menyengat.",
        "Membuat kulit terasa halus dan terhidrasi.",
    ],
    'home': [
        "Mudah dipasang dan tidak butuh alat tambahan.",
        "Ukurannya pas dan tidak makan banyak tempat.",
        "Bahannya kuat dan tahan dipakai lama.",
        "Membantu pekerjaan rumah jadi lebih cepat.",
        "Desainnya rapi sehingga rumah terlihat bersih.",
    ],
    'wellness': [
        "Nyaman dipakai dan tidak mudah selip.",
        "Membuat olahraga jadi lebih menyenangkan.",
        "Bahannya aman dan tidak mengiritasi kulit.",
        "Ringan dibawa kemana saja, praktis.",
        "Membantu menjaga kebugaran setiap hari.",
    ],
}

CATEGORY_PROOF = {
    'fashion': [
        "Ratingnya tinggi di toko dan sudah banyak terjual.",
        "Banyak pembeli yang memberikan ulasan positif.",
        "Sudah terbukti kualitasnya dari para pembeli.",
        "Ulasan dari para pembeli memang memuaskan.",
        "Banyak yang beli lagi karena memang puas.",
    ],
    'gadget': [
        "Sudah banyak yang pakai dan hasilnya memuaskan.",
        "Ulasan teknisnya sangat positif dari pembeli.",
        "Rating di toko menunjukkan kualitas yang konsisten.",
        "Banyak pengguna yang merekomendasikan produk ini.",
        "Terbukti handal dan banyak yang repeat order.",
    ],
    'beauty': [
        "Banyak yang merasakan perubahan setelah pemakaian.",
        "Ulasan di toko menunjukkan hasil yang nyata.",
        "Sudah terbukti aman dan banyak yang merekomendasikan.",
        "Rating tinggi menunjukkan kepuasan pelanggan.",
        "Banyak yang berlangganan karena memang hasilnya bagus.",
    ],
    'home': [
        "Sudah banyak yang pakai dan rumahnya jadi lebih rapi.",
        "Rating tinggi di toko, banyak yang puas.",
        "Ulasan pembeli menunjukkan kualitas yang baik.",
        "Terbukti tahan lama dari pengalaman para pembeli.",
        "Banyak yang beli untuk hadiah karena memang bagus.",
    ],
    'wellness': [
        "Banyak yang merasakan manfaatnya untuk kesehatan.",
        "Rating tinggi menunjukkan kepuasan pengguna.",
        "Sudah terbukti membantu rutinitas kebugaran.",
        "Ulasan positif dari para pengguna aktif.",
        "Banyak yang merekomendasikan untuk gaya hidup sehat.",
    ],
}

CATEGORY_CTA = {
    'fashion': [
        "Tertarik? Langsung cek di link yang tersedia.",
        "Jangan lewatkan, cek linknya sekarang.",
        "Sebelum kehabisan ukuranmu, langsung cek ya.",
        "Link pembelian ada di deskripsi.",
        "Yuk langsung lihat di toko, link di bawah.",
    ],
    'gadget': [
        "Tertarik? Langsung cek spesifikasinya di link.",
        "Jangan lewatkan, cek harganya sekarang.",
        "Link pembelian sudah tersedia di bawah.",
        "Langsung cek di toko, link ada di deskripsi.",
        "Sebelum harga naik, langsung cek ya.",
    ],
    'beauty': [
        "Tertarik mencoba? Cek linknya sekarang.",
        "Jangan lewatkan, langsung cek di deskripsi.",
        "Link pembelian ada di bawah ya.",
        "Yuk rawat kulitmu, cek linknya sekarang.",
        "Langsung cek di toko, link tersedia di bawah.",
    ],
    'home': [
        "Tertarik? Langsung cek di link ya.",
        "Yuk bikin rumah makin rapi, cek linknya.",
        "Link pembelian ada di deskripsi.",
        "Sebelum kehabisan, langsung cek sekarang.",
        "Langsung cek di toko, link di bawah.",
    ],
    'wellness': [
        "Tertarik memulai hidup sehat? Cek linknya.",
        "Jangan tunda, langsung cek di deskripsi.",
        "Link pembelian sudah tersedia di bawah.",
        "Yuk mulai sekarang, cek linknya.",
        "Langsung cek di toko, link ada di bawah.",
    ],
}


def _pick_unique(pool, used_set, rng):
    """Pick item from pool that hasn't been used yet. Prevents repetition."""
    available = [p for p in pool if p not in used_set]
    if not available:
        available = pool  # fallback: all used, start fresh
    picked = rng.choice(available)
    used_set.add(picked)
    return picked


def generate_voiceover_script(product_info, platform='yt_short', account_id='yt_1'):
    """Generate per-account themed voiceover scripts. No duplicate phrases."""
    nama = product_info.get('nama', '')
    harga = product_info.get('harga', '')
    desc = product_info.get('deskripsi_singkat', '')
    
    # Determine category DYNAMICALLY from category_router
    # (handles TT/FB day-of-month alternation correctly)
    try:
        from engine.modules.category_router import get_category
        cat = get_category(account_id)
    except ImportError:
        cat = product_info.get('category', 'home')
    if not cat:
        cat = product_info.get('category', 'home')
    
    # Seed RNG per product+account so same product gets different script per account
    seed_str = f"{nama}_{account_id}_{platform}"
    rng = random.Random(hash(seed_str))
    
    # Track used phrases to prevent repetition within this video
    used = set()
    
    # Convert price to Indonesian words
    harga_kata = harga_ke_kata(harga)
    
    # ALL scripts MUST mention product name — no generic category text
    nama_pendek = nama[:40].strip() if nama else 'produk ini'
    
    # HOOK: always mention product name
    if nama:
        hook_templates = [
            f"Hai, kali ini kita bahas {nama_pendek}.",
            f"Mau tahu tentang {nama_pendek}? Simak sampai habis.",
            f"Ini dia {nama_pendek}, yang lagi banyak dicari.",
            f"Buat kamu yang cari {nama_pendek}, wajib lihat ini.",
            f"Ada rekomendasi menarik, yaitu {nama_pendek}.",
        ]
        hook_text = rng.choice(hook_templates)
    else:
        hooks = CATEGORY_HOOKS.get(cat, CATEGORY_HOOKS['home'])
        hook_text = _pick_unique(hooks, used, rng)
    
    # HERO: product name + intro
    if nama:
        hero_templates = [
            f"Ini dia {nama_pendek}, yang lagi diminati banyak orang.",
            f"{nama_pendek}, produk yang sudah terbukti bagus.",
            f"Kenalkan, {nama_pendek}, pas untuk kebutuhan kamu.",
        ]
        hero_text = rng.choice(hero_templates)
    else:
        hero_text = "Produk yang satu ini, memang lagi diminati banyak orang."
    
    # FEATURE: product name + description (NEVER generic category text)
    if desc:
        short_desc = desc[:60].rstrip('.')
        feat_text = f"{nama_pendek}, {short_desc}."
    elif nama:
        features = CATEGORY_FEATURES.get(cat, CATEGORY_FEATURES['home'])
        generic_feat = _pick_unique(features, used, rng)
        feat_text = f"{nama_pendek}, {generic_feat.lower()}"
    else:
        features = CATEGORY_FEATURES.get(cat, CATEGORY_FEATURES['home'])
        feat_text = _pick_unique(features, used, rng)
    
    # PROOF: product name + price (NEVER generic)
    proofs = CATEGORY_PROOF.get(cat, CATEGORY_PROOF['home'])
    if harga_kata:
        price_templates = [
            f"{nama_pendek} dengan harga hanya {harga_kata}, kualitasnya terjamin.",
            f"Harga {nama_pendek} cuma {harga_kata}, dan sudah banyak yang puas.",
            f"Cuma {harga_kata} untuk {nama_pendek}, tapi kualitasnya sangat baik.",
        ]
        proof_text = rng.choice(price_templates)
    else:
        proof_text = _pick_unique(proofs, used, rng)
    
    # CTA (category-themed)
    ctas = CATEGORY_CTA.get(cat, CATEGORY_CTA['home'])
    cta_text = _pick_unique(ctas, used, rng)
    
    # Extra proof for yt_long
    extra_proof = _pick_unique(proofs, used, rng)

    if platform == 'yt_short':
        return {
            'hook': hook_text,
            'hero': hero_text,
            'feature': feat_text,
            'proof': proof_text,
            'cta': cta_text,
        }
    elif platform == 'yt_long':
        # Scene IDs MUST match TEMPLATES in generate_video_yt_long.py:
        # hook, overview, detail1, detail2, comparison, verdict, cta
        return {
            'hook': hook_text,
            'overview': hero_text,
            'detail1': feat_text,
            'detail2': proof_text,
            'comparison': extra_proof,
            'verdict': _pick_unique(proofs, used, rng),
            'cta': cta_text,
        }
    elif platform == 'tt':
        return {
            'hook': hook_text,
            'product': hero_text,
            'feature': feat_text,
            'cta': cta_text,
        }
    else:  # fb
        return {
            'hook': hook_text,
            'product': hero_text,
            'feature': feat_text,
            'proof': proof_text,
            'cta': cta_text,
        }



# ═══════════════════════════════════════════════════════════════════
#  TTS ENGINE (edge-tts native params, NO SSML)
# ═══════════════════════════════════════════════════════════════════

async def _generate_tts_async(text, output_path, rate='-10%', pitch='+0Hz', voice_id=None):
    """Generate TTS audio using edge-tts native Communicate params."""
    import edge_tts
    voice = voice_id or DEFAULT_VOICE
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def generate_tts(text, output_path, scene_id='feature', account_id='yt_1'):
    """Generate one TTS MP3 file with per-account voice.
    
    Returns True if generated successfully, False if failed.
    """
    try:
        style = SCENE_STYLES.get(scene_id, {'rate': '+10%', 'pitch': '+0Hz'})
        rate = style['rate']
        
        # Get per-account voice and pitch
        acct_voice = ACCOUNT_VOICES.get(account_id, {'voice': DEFAULT_VOICE, 'pitch_offset': '+0Hz'})
        voice_id = acct_voice['voice']
        
        # Combine scene pitch with account pitch offset
        scene_pitch_hz = int(style['pitch'].replace('Hz', '').replace('+', ''))
        acct_pitch_hz = int(acct_voice['pitch_offset'].replace('Hz', '').replace('+', ''))
        final_pitch = f"+{scene_pitch_hz + acct_pitch_hz}Hz" if (scene_pitch_hz + acct_pitch_hz) >= 0 else f"{scene_pitch_hz + acct_pitch_hz}Hz"

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        asyncio.run(_generate_tts_async(text, output_path, rate, final_pitch, voice_id=voice_id))

        if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            print(f"    [TTS] OK: {os.path.basename(output_path)} ({scene_id}, {voice_id})")
            return True
        else:
            print(f"    [TTS] Empty/small file: {os.path.basename(output_path)}")
            return False
    except Exception as e:
        print(f"    [TTS] Failed ({scene_id}): {e}")
        return False


def generate_voiceover_for_product(product_info, produk_id, platform='yt_short', output_dir=None, account_id='yt_1'):
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

    scripts = generate_voiceover_script(product_info, platform, account_id=account_id)
    result = {}
    print(f"  [TTS] {platform}/{account_id} for {produk_id}...")

    for scene_id, text in scripts.items():
        if not text or len(text.strip()) < 5:
            continue
        mp3_path = os.path.join(vo_dir, f"vo_{scene_id}.mp3")
        if generate_tts(text, mp3_path, scene_id, account_id=account_id):
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
        account_id = job.get('account_id', 'yt_1')
        for platform in platforms:
            generate_voiceover_for_product(job, produk_id, platform, account_id=account_id)
    print(f"[TTS] All done")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue', default='engine/queue/storyboard_queue.jsonl')
    parser.add_argument('--platform', default='all',
                       choices=['all', 'yt', 'yt_short', 'yt_long', 'tt', 'fb'])
    args = parser.parse_args()

    # Map shorthand platforms to actual VO platform names
    platform_map = {
        'all': ['yt_short', 'yt_long', 'tt', 'fb'],
        'yt': ['yt_short', 'yt_long'],     # YT queue → both formats
        'yt_short': ['yt_short'],
        'yt_long': ['yt_long'],
        'tt': ['tt'],
        'fb': ['fb'],
    }
    platforms = platform_map.get(args.platform, ['yt_short', 'yt_long', 'tt', 'fb'])
    generate_all_voiceovers(args.queue, platforms)
