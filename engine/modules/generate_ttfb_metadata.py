"""
generate_ttfb_metadata.py
Generates metadata for TikTok + Facebook videos:
- TikTok: catchy caption, trending hashtags per category, bio link CTA
- Facebook: defers to generate_fb_metadata.py for rich templates

Output:
  engine/state/tt_metadata.json  ← for TikTok
  engine/state/fb_metadata.json  ← for Facebook (from generate_fb_metadata.py)
"""
import json
import os
import sys
import random
import pandas as pd
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from engine.modules.category_router import (
    get_category, get_hashtags, get_copywriting, TIKTOK_ACCOUNT
)

# TikTok trending hashtags (always included)
TT_TRENDING = ['#fyp', '#viral', '#foryoupage', '#tiktok']

# TikTok caption templates (short, punchy, engaging)
TT_TEMPLATES = [
    "🔥 {hook}\n\n{nama}\n💰 {harga}\n\n{desc}\n\n👉 Link di bio!\n\n{hashtags}",
    "POV: kamu menemukan {nama} 🤯\n\n{desc}\n💰 Harga: {harga}\n\n🔗 Cek link di bio!\n\n{hashtags}",
    "Udah tau belum?? 👀\n\n{nama}\n{desc}\n💰 {harga}\n\n📌 Link Shopee di bio!\n\n{hashtags}",
    "Wait for it... 😱\n\n{nama} — {harga}\n\n✅ {desc}\n\n🛒 Shopee link di bio!\n\n{hashtags}",
    "{hook}\n\nNamanya: {nama}\n💰 {harga}\n\n{desc}\n\n👆 Link pembelian di bio!\n\n{hashtags}",
]


def generate_ttfb_metadata(tt_queue, fb_queue, produk_csv, output_dir):
    """Generate metadata for TikTok and Facebook videos."""
    print("Generating TikTok + Facebook metadata...")

    df_produk = pd.read_csv(produk_csv)
    os.makedirs(output_dir, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")

    # --- TikTok Metadata (enhanced with category_router) ---
    tt_results = []
    tt_category = get_category(TIKTOK_ACCOUNT['account_id'])
    tt_cat_hashtags = get_hashtags(tt_category)
    tt_hooks = get_copywriting(tt_category, 'hooks')

    if os.path.exists(tt_queue):
        with open(tt_queue, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                job = json.loads(line)
                produk_id = job['produk_id']
                acct_id = job.get('account_id', 'tt_1')

                prod_data = df_produk[df_produk['produk_id'] == produk_id].iloc[0]
                nama = prod_data['nama']
                desc = prod_data['deskripsi_singkat']
                harga = prod_data.get('harga', '') if 'harga' in prod_data.index else ''
                shopee_url = prod_data['shopee_url'] if 'shopee_url' in prod_data.index else ''

                # Combine trending + category hashtags (max 10)
                all_hashtags = TT_TRENDING + [h for h in tt_cat_hashtags if h not in TT_TRENDING]
                hashtag_str = ' '.join(all_hashtags[:10])

                # Random hook
                hook = random.choice(tt_hooks)

                # Random template
                template = random.choice(TT_TEMPLATES)
                caption = template.format(
                    hook=hook, nama=nama, desc=desc,
                    harga=harga, hashtags=hashtag_str
                )

                tt_results.append({
                    'file': f"{today}_{produk_id}_tt.mp4",
                    'account_id': acct_id,
                    'produk': nama,
                    'deskripsi': desc,
                    'harga': str(harga),
                    'shopee_url': str(shopee_url),
                    'caption': caption.strip(),
                    'hashtags': hashtag_str,
                    'bio_link': str(shopee_url),
                    'video_type': 'long',
                    'posting_slot': job.get('slot', 'pagi'),
                })

                # Short version entry (auto-extracted from Long)
                short_caption = f"🔥 {nama[:30]}\n\n💰 {harga}\n\n👉 Link di bio!\n\n{hashtag_str}"
                tt_results.append({
                    'file': f"{today}_{produk_id}_tt_short.mp4",
                    'account_id': acct_id,
                    'produk': nama,
                    'deskripsi': desc,
                    'harga': str(harga),
                    'shopee_url': str(shopee_url),
                    'caption': short_caption.strip(),
                    'hashtags': hashtag_str,
                    'bio_link': str(shopee_url),
                    'video_type': 'short',
                    'posting_slot': 'siang' if job.get('slot') == 'pagi' else 'malam',
                })

        tt_path = os.path.join(output_dir, "tt_metadata.json")
        with open(tt_path, 'w', encoding='utf-8') as f:
            json.dump(tt_results, f, indent=2, ensure_ascii=False)
        print(f"  TikTok metadata saved: {len(tt_results)} entries -> {tt_path}")
    else:
        print(f"  TikTok queue not found, skipping")

    # --- Facebook Metadata ---
    # Handled by generate_fb_metadata.py (separate module with richer templates)
    # But also generate basic FB metadata here as fallback
    fb_results = []
    fb_path = os.path.join(output_dir, "fb_metadata.json")

    # Only generate if generate_fb_metadata hasn't already created it
    if not os.path.exists(fb_path) and os.path.exists(fb_queue):
        print("  FB metadata not found, generating basic fallback...")
        with open(fb_queue, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                job = json.loads(line)
                produk_id = job['produk_id']
                acct_id = job.get('account_id', 'fb_1')

                prod_data = df_produk[df_produk['produk_id'] == produk_id].iloc[0]
                nama = prod_data['nama']
                desc = prod_data['deskripsi_singkat']
                harga = prod_data.get('harga', '') if 'harga' in prod_data.index else ''
                shopee_url = prod_data['shopee_url'] if 'shopee_url' in prod_data.index else ''

                post_text = f"""🎯 {nama}

{desc}
💰 Harga: {harga}

🛒 Beli di Shopee:
{shopee_url}

#shopee #affiliate #recommended"""

                fb_results.append({
                    'file': f"{today}_{produk_id}_fb.mp4",
                    'account_id': acct_id,
                    'produk': nama,
                    'harga': str(harga),
                    'shopee_url': str(shopee_url),
                    'post_text': post_text.strip(),
                    'video_type': 'long',
                    'posting_slot': job.get('slot', 'pagi'),
                })

                # Short version entry
                short_post = f"🔥 {nama}\n💰 {harga}\n🛒 {shopee_url}\n#shopee #affiliate"
                fb_results.append({
                    'file': f"{today}_{produk_id}_fb_short.mp4",
                    'account_id': acct_id,
                    'produk': nama,
                    'harga': str(harga),
                    'shopee_url': str(shopee_url),
                    'post_text': short_post.strip(),
                    'video_type': 'short',
                    'posting_slot': 'siang' if job.get('slot') == 'pagi' else 'malam',
                })

        with open(fb_path, 'w', encoding='utf-8') as f:
            json.dump(fb_results, f, indent=2, ensure_ascii=False)
        print(f"  Facebook metadata (fallback): {len(fb_results)} entries -> {fb_path}")
    elif os.path.exists(fb_path):
        print(f"  Facebook metadata already generated by generate_fb_metadata.py")
    else:
        print(f"  Facebook queue not found, skipping")

    total = len(tt_results) + len(fb_results)
    print(f"TT+FB metadata complete: {total} entries total")


if __name__ == "__main__":
    generate_ttfb_metadata(
        "engine/queue/tt_queue.jsonl",
        "engine/queue/fb_queue.jsonl",
        "engine/data/produk.csv",
        "engine/state"
    )

