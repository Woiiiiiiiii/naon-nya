"""
cf_copywriter.py
Generate unique product copy using Cloudflare Workers AI (Llama 3).

Generates per-product:
  - Hook text (attention-grabbing, unique each time)
  - CTA text (urgent, platform-appropriate)
  - Product description (concise, persuasive)
  - Voiceover script (natural Indonesian conversational tone)

Replaces static template libraries with AI-generated, always-fresh copy.
"""

import os
import json
import random
import requests

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
CF_MODEL = '@cf/meta/llama-3-8b-instruct'

# Dedicated CF key per channel — NO sharing
ACCOUNT_CF_MAP = {
    'yt_1': 1, 'yt_2': 2, 'yt_3': 3, 'yt_4': 4, 'yt_5': 5,
    'tt_1': 6, 'fb_1': 7,
    'fashion': 1, 'gadget': 2, 'beauty': 3, 'home': 4, 'wellness': 5,
    'tt': 6, 'fb': 7,
}

def _get_cf_credentials(account_index=None):
    """Get CF credentials for a DEDICATED account index.
    Each channel uses ONLY its own key — no borrowing."""
    if account_index is not None:
        acc_id = os.environ.get(f'CF_ACCOUNT_ID_{account_index}', '')
        api_key = os.environ.get(f'CF_API_KEY_{account_index}', '')
        if acc_id and api_key:
            return acc_id, api_key
        # Try shared account ID with per-account key
        acc_id = os.environ.get('CF_ACCOUNT_ID', '')
        if acc_id and api_key:
            return acc_id, api_key

    # Last resort: first available (only when index not provided)
    for i in range(1, 8):
        acc_id = os.environ.get(f'CF_ACCOUNT_ID_{i}', '')
        api_key = os.environ.get(f'CF_API_KEY_{i}', '')
        if acc_id and api_key:
            return acc_id, api_key
    acc_id = os.environ.get('CF_ACCOUNT_ID', '')
    api_key = os.environ.get('CF_API_KEY', '')
    if acc_id and api_key:
        return acc_id, api_key
    return None, None


# Fallback templates if CF is unavailable
FALLBACK_HOOKS = [
    "Kamu masih pakai yang biasa?",
    "STOP! Jangan scroll dulu!",
    "Ini yang lagi viral!",
    "Banyak yang gak tau ini...",
    "Kenapa semua orang beli ini?",
    "Cek dulu sebelum menyesal!",
]

FALLBACK_CTAS = [
    "Klik link di deskripsi untuk beli!",
    "Cek harga spesial di link deskripsi!",
    "Stok terbatas, grab sekarang!",
    "Buruan order sebelum harga naik!",
]


def generate_copy(product_info, platform='yt_short', account_id=None):
    """Generate unique copy for a product using CF Workers AI Llama 3.
    
    Args:
        product_info: dict with nama, harga, category, deskripsi_singkat
        platform: yt_short, yt_long, tt, fb
        account_id: channel ID (yt_1..yt_5, tt_1, fb_1) for dedicated CF key
    
    Returns:
        dict with keys: hook, cta, description, voiceover_hook, voiceover_cta
    """
    nama = product_info.get('nama', 'Produk')
    harga = product_info.get('harga', '')
    category = product_info.get('category', 'home')
    desc = product_info.get('deskripsi_singkat', '')
    
    # Resolve to dedicated CF key index
    cf_index = None
    if account_id:
        cf_index = ACCOUNT_CF_MAP.get(account_id)
    if cf_index is None:
        cf_index = ACCOUNT_CF_MAP.get(category)
    
    account_id_resolved, api_key = _get_cf_credentials(cf_index)
    
    if not api_key or not account_id_resolved:
        return _fallback_copy(nama, harga, category, platform)
    
    platform_context = {
        'yt_short': 'YouTube Shorts (45 detik, energik, singkat)',
        'yt_long': 'YouTube Long (2-3 menit, detail, informatif)',
        'tt': 'TikTok (30 detik, sangat cepat, catchy)',
        'fb': 'Facebook (1 menit, santai, informatif)',
    }
    
    prompt = f"""Kamu adalah copywriter produk affiliate Indonesia. Buat copy untuk produk ini:

Nama: {nama}
Harga: {harga}
Kategori: {category}
Deskripsi: {desc[:100] if desc else 'Produk berkualitas'}
Platform: {platform_context.get(platform, 'YouTube Shorts')}

Buat dalam format JSON (HANYA JSON, tanpa penjelasan):
{{
  "hook": "kalimat hook yang bikin penasaran (max 15 kata, TANPA emoji)",
  "cta": "kalimat ajakan beli yang urgent (max 12 kata, TANPA emoji)",
  "description": "deskripsi singkat persuasif (max 25 kata)",
  "voiceover_hook": "kalimat pembuka untuk voiceover (natural, conversational, max 20 kata)",
  "voiceover_cta": "kalimat penutup voiceover yang bikin pengen beli (max 20 kata)"
}}

Rules:
- Bahasa Indonesia casual/gaul tapi profesional
- JANGAN pakai emoji
- Setiap kali generate harus UNIK dan BERBEDA
- Sesuaikan tone dengan platform"""

    try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id_resolved}/ai/run/{CF_MODEL}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "messages": [
                {"role": "system", "content": "Kamu copywriter produk Indonesia. Selalu jawab dalam format JSON valid."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 300,
            "temperature": 0.8,  # High for variety
        }

        print(f"    [LLM] Generating copy for {nama[:30]}...")
        resp = requests.post(url, headers=headers, json=payload, timeout=30)

        if resp.status_code != 200:
            print(f"    [LLM] HTTP {resp.status_code}")
            return _fallback_copy(nama, harga, category, platform)

        data = resp.json()
        result_text = data.get('result', {}).get('response', '')
        
        # Parse JSON from response
        copy = _parse_json_response(result_text)
        if copy:
            print(f"    [LLM] Generated unique copy: hook='{copy.get('hook', '')[:40]}...'")
            return copy

        return _fallback_copy(nama, harga, category, platform)

    except Exception as e:
        print(f"    [LLM] Error: {e}")
        return _fallback_copy(nama, harga, category, platform)


def _parse_json_response(text):
    """Extract JSON from LLM response text."""
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    
    # Try to find JSON block in text
    import re
    json_match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except Exception:
            pass
    
    return None


def _fallback_copy(nama, harga, category, platform):
    """Fallback when CF AI is unavailable."""
    hook_template = random.choice(FALLBACK_HOOKS)
    hook = hook_template.replace('{nama}', nama[:30]) if '{nama}' in hook_template else hook_template
    
    return {
        'hook': hook,
        'cta': random.choice(FALLBACK_CTAS),
        'description': f"{nama[:40]} - produk terlaris di kategori {category}",
        'voiceover_hook': f"Hei, kamu harus tau tentang {nama[:30]} ini!",
        'voiceover_cta': f"Buruan cek linknya ya, stok terbatas!",
    }


def enrich_storyboard(queue_file, output_file=None, platform='yt_short'):
    """Enrich storyboard queue with AI-generated copy.
    
    Reads existing queue, generates unique copy per product,
    writes enriched queue back.
    """
    if not os.path.exists(queue_file):
        print(f"  [LLM] Queue not found: {queue_file}")
        return
    
    jobs = []
    with open(queue_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                jobs.append(json.loads(line.strip()))
    
    if not output_file:
        output_file = queue_file
    
    print(f"[LLM] Enriching {len(jobs)} products with AI copy...")
    
    enriched = []
    for job in jobs:
        job_account_id = job.get('account_id', None)
        copy = generate_copy(job, platform, account_id=job_account_id)
        
        # Override with AI-generated copy
        job['hook'] = copy.get('hook', job.get('hook', ''))
        job['cta'] = copy.get('cta', job.get('cta', ''))
        job['deskripsi_singkat'] = copy.get('description', job.get('deskripsi_singkat', ''))
        job['voiceover_hook'] = copy.get('voiceover_hook', '')
        job['voiceover_cta'] = copy.get('voiceover_cta', '')
        enriched.append(job)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for job in enriched:
            f.write(json.dumps(job, ensure_ascii=False) + '\n')
    
    print(f"[LLM] Done — {len(enriched)} products enriched")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue', default='engine/queue/storyboard_queue.jsonl')
    parser.add_argument('--platform', default='yt_short')
    args = parser.parse_args()
    
    enrich_storyboard(args.queue, platform=args.platform)
