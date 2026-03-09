"""
metadata_generator.py
Central Gemini-powered text generator with round-robin API key rotation.
Generates titles, descriptions, hooks, CTAs, hashtags per platform.
"""
import os
import json
import time
import requests

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')

# Round-robin state
_current_key_index = 0
_api_keys = []


def _load_gemini_keys():
    """Load Gemini API keys from config with env var resolution."""
    global _api_keys
    if _api_keys:
        return _api_keys

    config_path = os.path.join(CONFIG_DIR, 'gemini_config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        _api_keys = [os.environ.get(k, k) for k in config.get('api_keys', [])]
    else:
        # Fallback: try env vars directly
        for i in range(1, 6):
            key = os.environ.get(f'GEMINI_API_KEY_{i}', '')
            if key:
                _api_keys.append(key)

    _api_keys = [k for k in _api_keys if k and not k.startswith('GEMINI_')]
    return _api_keys


def _get_next_key():
    """Round-robin key selection with fallback on error."""
    global _current_key_index
    keys = _load_gemini_keys()
    if not keys:
        return None
    key = keys[_current_key_index % len(keys)]
    _current_key_index = (_current_key_index + 1) % len(keys)
    return key


def call_gemini(prompt, max_retries=3):
    """Call Gemini API with round-robin key rotation and fallback."""
    keys = _load_gemini_keys()
    if not keys:
        print("  [WARN] No Gemini API keys available")
        return None

    for attempt in range(max_retries):
        api_key = _get_next_key()
        if not api_key:
            continue

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.8,
                    "maxOutputTokens": 1024,
                }
            }
            resp = requests.post(url, json=payload, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                text = data['candidates'][0]['content']['parts'][0]['text']
                return text.strip()
            elif resp.status_code == 429:
                print(f"  [WARN] Gemini rate limited, rotating key...")
                time.sleep(2)
                continue
            else:
                print(f"  [WARN] Gemini {resp.status_code}: {resp.text[:100]}")
                continue
        except Exception as e:
            print(f"  [WARN] Gemini error: {e}")
            continue

    return None


def generate_title(product_name, category, platform, price='', rating=''):
    """Generate catchy title for a video."""
    style_map = {
        'youtube': 'SEO-friendly, informatif, 60 karakter max',
        'tiktok': 'viral, singkat, pakai emoji, 40 karakter max',
        'facebook': 'engaging, problem-solution, 80 karakter max',
    }
    style = style_map.get(platform, style_map['youtube'])

    prompt = f"""Buat 1 judul video produk affiliate dalam Bahasa Indonesia.
Produk: {product_name}
Kategori: {category}
Harga: {price}
Rating: {rating}
Platform: {platform}
Style: {style}

Berikan HANYA judul saja, tanpa penjelasan. Judul harus clickable dan menarik."""

    result = call_gemini(prompt)
    if result:
        # Clean up: remove quotes, newlines
        return result.strip('"\'').split('\n')[0]
    return f"Review {product_name} - Worth It? 🔥"


def generate_description(product_name, category, platform, price='',
                         features='', affiliate_link=''):
    """Generate video description with CTA and affiliate link."""
    prompt = f"""Buat deskripsi video produk affiliate dalam Bahasa Indonesia.
Produk: {product_name}
Kategori: {category}
Harga: {price}
Fitur: {features}
Platform: {platform}
Link Affiliate: {affiliate_link}

Deskripsi harus:
- Engaging dan informatif
- Include CTA yang kuat
- Include link affiliate di posisi strategis
- Optimized untuk {platform}

Berikan HANYA deskripsi, tanpa penjelasan."""

    return call_gemini(prompt)


def generate_hashtags(category, platform, count=10):
    """Generate relevant hashtags for the category and platform."""
    prompt = f"""Buat {count} hashtag trending untuk konten produk {category} di {platform}.
Bahasa Indonesia dan mix English.
Format: #hashtag1 #hashtag2 ...
Berikan HANYA hashtag, tanpa penjelasan."""

    result = call_gemini(prompt)
    if result:
        return result.strip()
    return f"#{category.replace(' ', '')} #review #affiliate #shopee"


def generate_hooks(category, count=5):
    """Generate hook text variations for video overlay."""
    prompt = f"""Buat {count} hook teks pendek untuk video review produk kategori {category}.
Bahasa Indonesia, catchy, bikin penasaran, max 8 kata per hook.
Format: satu hook per baris, tanpa nomor.
Berikan HANYA hook, tanpa penjelasan."""

    result = call_gemini(prompt)
    if result:
        return [h.strip() for h in result.strip().split('\n') if h.strip()]
    return [f"Produk {category} viral!", f"Wajib punya {category} ini!"]


def generate_cta_text(category, count=3):
    """Generate CTA text variations."""
    prompt = f"""Buat {count} CTA (call-to-action) untuk video produk {category}.
Bahasa Indonesia, urgent, bikin orang klik link.
Max 10 kata per CTA.
Format: satu CTA per baris, tanpa nomor.
Berikan HANYA CTA, tanpa penjelasan."""

    result = call_gemini(prompt)
    if result:
        return [c.strip() for c in result.strip().split('\n') if c.strip()]
    return ["Cek link di deskripsi!", "Beli sekarang sebelum kehabisan!"]


def generate_all_metadata(queue_dir, output_dir):
    """Generate metadata for all queued products."""
    print("=== Gemini Metadata Generator ===")

    platforms = {
        'yt': ('youtube', os.path.join(queue_dir, 'yt_queue.jsonl')),
        'tt': ('tiktok', os.path.join(queue_dir, 'tt_queue.jsonl')),
        'fb': ('facebook', os.path.join(queue_dir, 'fb_queue.jsonl')),
    }

    total = 0
    for plat_code, (platform, queue_file) in platforms.items():
        if not os.path.exists(queue_file):
            continue

        jobs = []
        with open(queue_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    jobs.append(json.loads(line.strip()))

        for job in jobs:
            produk_id = job.get('produk_id', 'unknown')
            nama = job.get('nama', produk_id)
            category = job.get('category', 'general')
            harga = job.get('harga', '')
            link = job.get('affiliate_link', '')

            meta = {
                'produk_id': produk_id,
                'platform': platform,
                'title': generate_title(nama, category, platform, harga),
                'hashtags': generate_hashtags(category, platform),
            }

            meta_dir = os.path.join(output_dir, plat_code)
            os.makedirs(meta_dir, exist_ok=True)
            meta_path = os.path.join(meta_dir, f"{produk_id}_gemini_meta.json")
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            total += 1
            print(f"  [OK] {platform}: {produk_id}")

    print(f"=== Metadata generated: {total} items ===")


if __name__ == "__main__":
    queue_dir = "engine/queue"
    output_dir = "engine/output"
    if os.path.isdir(queue_dir):
        generate_all_metadata(queue_dir, output_dir)
    else:
        print("=== Metadata Generator: No queue dir found, skipping ===")
