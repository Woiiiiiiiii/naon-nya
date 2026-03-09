"""
generate_fb_metadata.py
Facebook-specific metadata: engaging titles, problem-solution descriptions,
affiliate links, and hashtags — formatted for direct copy-paste from email.

Output: engine/state/fb_metadata.json
"""
import json
import os
import sys
import random
import datetime
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from engine.modules.category_router import (
    get_category, get_hashtags, get_copywriting, FACEBOOK_ACCOUNT
)

# Facebook-optimized templates (longer, more descriptive for adult audience)
FB_TEMPLATES = [
    {
        'style': 'problem_solution',
        'format': """🎯 {nama}

Pernah nggak sih mengalami {masalah}?

Nah, {nama} ini bisa jadi solusinya! ✅

💡 Kenapa produk ini worth it:
• {benefit_1}
• {benefit_2}
• {benefit_3}

💰 Harga: {harga}

🛒 Beli di Shopee:
{shopee_url}

{hashtags}""",
    },
    {
        'style': 'review',
        'format': """📦 Review Jujur: {nama}

Setelah nyobain produk ini, ternyata...

✅ Kelebihan:
• {benefit_1}
• {benefit_2}
• {benefit_3}

⭐ Rating: {rating}/5 — {verdict}

💰 {harga}

🛒 Order di Shopee:
{shopee_url}

{hashtags}""",
    },
    {
        'style': 'recommendation',
        'format': """🔥 Rekomendasi Produk Hari Ini!

{nama}

{deskripsi}

✅ Yang bikin produk ini istimewa:
• {benefit_1}
• {benefit_2}

💰 Harga cuma {harga}

🛒 Langsung order:
{shopee_url}

💬 Sudah pernah coba? Share pengalaman kamu di komentar!

{hashtags}""",
    },
]

# Random benefits per category
CATEGORY_BENEFITS = {
    'fashion': [
        "Bahan premium dan nyaman dipakai seharian",
        "Design kekinian yang cocok untuk berbagai occasion",
        "Ukuran pas dan sesuai ekspektasi",
        "Tahan lama, nggak gampang rusak",
        "Harga terjangkau untuk kualitas segini",
        "Banyak pilihan warna dan variant",
    ],
    'gadget': [
        "Build quality solid dan premium",
        "Fitur lengkap melebihi harganya",
        "Kompatibel dengan banyak device",
        "Daya tahan baterai yang lama",
        "Setup mudah, plug and play",
        "Garansi resmi terpercaya",
    ],
    'beauty': [
        "Ingredients aman dan sudah BPOM",
        "Cocok untuk semua jenis kulit",
        "Hasil terlihat dalam 7-14 hari",
        "Tekstur ringan, cepat menyerap",
        "Tidak menyebabkan breakout",
        "Packaging travel-friendly",
    ],
    'home': [
        "Material kokoh dan tahan lama",
        "Hemat tempat, design compact",
        "Mudah dibersihkan dan dirawat",
        "Multifungsi, bisa dipakai untuk banyak hal",
        "Bikin rumah lebih rapi dan terorganisir",
        "Instalasi simpel, tanpa alat tambahan",
    ],
    'wellness': [
        "Material aman dan nyaman digunakan",
        "Efektif untuk workout di rumah",
        "Terbukti membantu recovery",
        "Portable, bisa dibawa kemana-mana",
        "Cocok untuk pemula maupun advanced",
        "Investasi kesehatan jangka panjang",
    ],
}


def generate_fb_metadata(fb_queue, produk_csv, output_dir):
    """Generate Facebook-specific metadata with problem-solution format."""
    print("Generating Facebook metadata (copy-paste ready)...")

    df_produk = pd.read_csv(produk_csv)
    os.makedirs(output_dir, exist_ok=True)

    fb_category = get_category(FACEBOOK_ACCOUNT['account_id'])
    fb_hashtags = get_hashtags(fb_category)
    benefits_pool = CATEGORY_BENEFITS.get(fb_category, CATEGORY_BENEFITS['home'])
    hooks = get_copywriting(fb_category, 'hooks')

    results = []
    if not os.path.exists(fb_queue):
        print(f"  FB queue not found: {fb_queue}, skipping.")
        return

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

            # Random template
            template = random.choice(FB_TEMPLATES)

            # Random benefits
            bens = random.sample(benefits_pool, min(3, len(benefits_pool)))

            # Random rating
            rating = round(random.uniform(4.5, 4.9), 1)
            verdicts = ["HIGHLY RECOMMENDED!", "Worth Every Penny!", "Must Have!",
                        "Top Pick!", "Best in Class!"]

            # Random masalah (problem)
            masalah_pool = [
                f"kesulitan menemukan {nama} yang berkualitas tapi harga terjangkau",
                f"bingung memilih produk yang tepat untuk kebutuhan kamu",
                f"kecewa dengan produk serupa yang nggak sesuai ekspektasi",
            ]

            hashtag_str = ' '.join(fb_hashtags[:7])

            post_text = template['format'].format(
                nama=nama,
                deskripsi=desc,
                harga=harga,
                shopee_url=shopee_url,
                masalah=random.choice(masalah_pool),
                benefit_1=bens[0] if len(bens) > 0 else "",
                benefit_2=bens[1] if len(bens) > 1 else "",
                benefit_3=bens[2] if len(bens) > 2 else "",
                rating=rating,
                verdict=random.choice(verdicts),
                hashtags=hashtag_str,
            )

            today = datetime.datetime.now().strftime("%Y%m%d")
            results.append({
                'file': f"{today}_{produk_id}_{acct_id}_fb.mp4",
                'account_id': acct_id,
                'produk': nama,
                'harga': str(harga),
                'shopee_url': str(shopee_url),
                'post_text': post_text.strip(),
                'template_style': template['style'],
                'hashtags': hashtag_str,
            })

    # Save
    fb_path = os.path.join(output_dir, "fb_metadata.json")
    with open(fb_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"  Facebook metadata: {len(results)} entries -> {fb_path}")
    return results


if __name__ == "__main__":
    generate_fb_metadata(
        "engine/queue/fb_queue.jsonl",
        "engine/data/produk.csv",
        "engine/state"
    )
