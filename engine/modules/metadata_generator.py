"""
metadata_generator.py
Central Gemini-powered text generator with DEDICATED per-channel API keys.
Each channel (yt_1..yt_5, tt_1, fb_1) uses its OWN Gemini API key.
Generates titles, descriptions, hooks, CTAs, hashtags per platform.
"""
import os
import json
import time
import requests

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')

# Dedicated Gemini key per channel — NO sharing, NO round-robin
ACCOUNT_GEMINI_MAP = {
    'yt_1': 1,  'yt_2': 2,  'yt_3': 3,  'yt_4': 4,  'yt_5': 5,
    'tt_1': 6,  'fb_1': 7,
    # Aliases for category-based lookup
    'fashion': 1, 'gadget': 2, 'beauty': 3, 'home': 4, 'wellness': 5,
    'tt': 6, 'fb': 7,
}

# Cache: per-channel config loaded from gemini_config.json
_channel_key_map = None


def _load_channel_key_map():
    """Load per-channel Gemini API keys from config with env var resolution."""
    global _channel_key_map
    if _channel_key_map is not None:
        return _channel_key_map

    _channel_key_map = {}
    config_path = os.path.join(CONFIG_DIR, 'gemini_config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        # Config format: {"yt_1": "GEMINI_API_KEY_1", ...}
        for channel, env_var in config.items():
            resolved = os.environ.get(env_var, '')
            if resolved and not resolved.startswith('GEMINI_'):
                _channel_key_map[channel] = resolved

    # Fallback: try env vars directly (GEMINI_API_KEY_1..7)
    if not _channel_key_map:
        index_to_channel = {v: k for k, v in ACCOUNT_GEMINI_MAP.items()
                           if k.startswith(('yt_', 'tt_', 'fb_'))}
        for i in range(1, 8):
            key = os.environ.get(f'GEMINI_API_KEY_{i}', '')
            if key:
                channel = index_to_channel.get(i, f'idx_{i}')
                _channel_key_map[channel] = key

    return _channel_key_map


def _get_key_for_account(account_id=None):
    """Get the DEDICATED Gemini API key for a specific account.
    Each channel uses ONLY its own key — no borrowing.
    """
    key_map = _load_channel_key_map()

    if account_id:
        # Direct match (yt_1, tt_1, fb_1)
        if account_id in key_map:
            return key_map[account_id]

        # Resolve via ACCOUNT_GEMINI_MAP (category name → index → channel)
        key_index = ACCOUNT_GEMINI_MAP.get(account_id)
        if key_index:
            # Find channel name for this index
            for ch, idx in ACCOUNT_GEMINI_MAP.items():
                if idx == key_index and ch in key_map:
                    return key_map[ch]

    # No account_id or not found — return None (do NOT borrow other channel's key)
    return None


def call_gemini(prompt, account_id=None, max_retries=3):
    """Call Gemini API with DEDICATED per-channel key.
    Each channel uses ONLY its own key — no round-robin, no borrowing.

    Args:
        prompt: Text prompt for Gemini
        account_id: Channel ID (yt_1..yt_5, tt_1, fb_1) or category name
        max_retries: Number of retries on transient errors
    """
    api_key = _get_key_for_account(account_id)
    if not api_key:
        print(f"  [WARN] No Gemini API key for account={account_id}")
        return None

    key_index = ACCOUNT_GEMINI_MAP.get(account_id, '?')

    for attempt in range(max_retries):
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
                print(f"  [WARN] Gemini rate limited (key #{key_index}), retrying...")
                time.sleep(2)
                continue
            else:
                print(f"  [WARN] Gemini {resp.status_code}: {resp.text[:100]}")
                continue
        except Exception as e:
            print(f"  [WARN] Gemini error: {e}")
            continue

    return None


def generate_title(product_name, category, platform, price='', rating='', account_id=None):
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

    result = call_gemini(prompt, account_id=account_id or category)
    if result:
        # Clean up: remove quotes, newlines
        return result.strip('"\'').split('\n')[0]
    return f"Review {product_name} - Worth It? 🔥"


def generate_description(product_name, category, platform, price='',
                         features='', affiliate_link='', account_id=None):
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

    return call_gemini(prompt, account_id=account_id or category)


def generate_hashtags(category, platform, count=10, account_id=None):
    """Generate relevant hashtags for the category and platform."""
    prompt = f"""Buat {count} hashtag trending untuk konten produk {category} di {platform}.
Bahasa Indonesia dan mix English.
Format: #hashtag1 #hashtag2 ...
Berikan HANYA hashtag, tanpa penjelasan."""

    result = call_gemini(prompt, account_id=account_id or category)
    if result:
        return result.strip()
    return f"#{category.replace(' ', '')} #review #affiliate #shopee"


def generate_hooks(category, count=5, account_id=None):
    """Generate hook text variations for video overlay."""
    prompt = f"""Buat {count} hook teks pendek untuk video review produk kategori {category}.
Bahasa Indonesia, catchy, bikin penasaran, max 8 kata per hook.
Format: satu hook per baris, tanpa nomor.
Berikan HANYA hook, tanpa penjelasan."""

    result = call_gemini(prompt, account_id=account_id or category)
    if result:
        return [h.strip() for h in result.strip().split('\n') if h.strip()]
    return [f"Produk {category} viral!", f"Wajib punya {category} ini!"]


def generate_cta_text(category, count=3, account_id=None):
    """Generate CTA text variations."""
    prompt = f"""Buat {count} CTA (call-to-action) untuk video produk {category}.
Bahasa Indonesia, urgent, bikin orang klik link.
Max 10 kata per CTA.
Format: satu CTA per baris, tanpa nomor.
Berikan HANYA CTA, tanpa penjelasan."""

    result = call_gemini(prompt, account_id=account_id or category)
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

            # Determine account_id from job for dedicated Gemini key
            account_id = job.get('account_id')
            if not account_id:
                # Infer from platform
                if plat_code == 'tt':
                    account_id = 'tt_1'
                elif plat_code == 'fb':
                    account_id = 'fb_1'
                else:
                    account_id = category  # category → key index via map

            meta = {
                'produk_id': produk_id,
                'platform': platform,
                'title': generate_title(nama, category, platform, harga, account_id=account_id),
                'hashtags': generate_hashtags(category, platform, account_id=account_id),
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
