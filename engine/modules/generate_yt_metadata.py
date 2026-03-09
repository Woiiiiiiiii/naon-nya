"""
generate_yt_metadata.py
Generates YouTube metadata per video per account:
- Long-form: detailed title, full description with review format
- Shorts: punchy title, concise description
- Per-category hashtags from category_router
- Affiliate link as first line of description
- Gemini integration for dynamic, non-repetitive text generation
"""
import json
import os
import sys
import random
import pandas as pd
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from engine.modules.category_router import (
    get_category, get_hashtags, get_label, get_channel_name, get_copywriting
)

# Gemini integration for dynamic metadata
try:
    from engine.modules.metadata_generator import call_gemini
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


def _gemini_title(nama, category, harga, video_type, platform='youtube'):
    """Generate title via Gemini API with fallback to templates."""
    if not HAS_GEMINI:
        return None
    try:
        prompt = (
            f"Buat 1 judul video {platform} yang catchy untuk produk berikut:\n"
            f"Nama: {nama}\nKategori: {category}\nHarga: {harga}\n"
            f"Tipe: {'Long-form review' if video_type == 'long' else 'Shorts'}\n"
            f"Bahasa Indonesia, max {'100' if video_type == 'long' else '50'} karakter.\n"
            f"Jangan pakai emoji berlebihan. Output hanya judul saja tanpa penjelasan."
        )
        result = call_gemini(prompt)
        if result and len(result.strip()) > 5:
            return result.strip().strip('"')
    except Exception:
        pass
    return None


def _gemini_description(nama, category, harga, desc, shopee_url, video_type):
    """Generate description via Gemini API with fallback."""
    if not HAS_GEMINI:
        return None
    try:
        prompt = (
            f"Buat deskripsi video YouTube untuk produk berikut:\n"
            f"Nama: {nama}\nKategori: {category}\nHarga: {harga}\n"
            f"Link: {shopee_url}\nDeskripsi produk: {desc}\n"
            f"Tipe: {'Long-form review' if video_type == 'long' else 'Shorts'}\n"
            f"Format: Link produk di baris pertama, lalu deskripsi engaging.\n"
            f"Bahasa Indonesia natural, tidak repetitif. Output deskripsi saja."
        )
        result = call_gemini(prompt)
        if result and len(result.strip()) > 20:
            return result.strip()
    except Exception:
        pass
    return None


def generate_metadata(yt_queue, produk_csv, output_dir):
    """Generate title, description, and hashtags for each YT video."""
    print("Generating YouTube metadata (judul + deskripsi + hashtag)...")
    today = datetime.datetime.now().strftime("%Y%m%d")

    if not os.path.exists(yt_queue):
        print(f"No YT queue found ({yt_queue}), skipping metadata.")
        return

    df_produk = pd.read_csv(produk_csv)

    jobs = []
    with open(yt_queue, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                jobs.append(json.loads(line))

    metadata_results = []
    for i, job in enumerate(jobs):
        produk_id = job['produk_id']
        variant_id = job.get('variant_id', 1)
        acct_id = job.get('account_id', f'yt_{variant_id}')
        acct_num = int(acct_id.split('_')[1]) if '_' in acct_id else 1
        scheduled_time = job.get('scheduled_time', '08:00')
        video_type = job.get('video_type', 'short')

        category = get_category(acct_id)
        cat_label = get_label(acct_id)
        channel = get_channel_name(acct_id)
        cat_hashtags = get_hashtags(category)
        cta_variants = get_copywriting(category, 'cta')

        prod_data = df_produk[df_produk['produk_id'] == produk_id].iloc[0]
        nama = prod_data['nama']
        desc = prod_data['deskripsi_singkat']
        harga = prod_data.get('harga', '') if 'harga' in prod_data.index else ''
        shopee_url = prod_data['shopee_url'] if 'shopee_url' in prod_data.index else ''

        # Determine file suffix based on video type
        suffix = 'yt_long' if video_type == 'long' else 'yt'

        if video_type == 'long':
            # ── LONG-FORM TITLE (try Gemini first, fallback to templates) ──
            gemini_title = _gemini_title(nama, category, harga, 'long')
            if gemini_title and len(gemini_title) <= 100:
                title = gemini_title
            else:
                title_templates = [
                    f"Review Jujur: {nama} - Worth It?",
                    f"{nama} - Review Lengkap dan Honest Opinion",
                    f"Wajib Tau Sebelum Beli {nama}!",
                    f"Review {nama}: Kelebihan dan Kekurangan",
                    f"Cek Dulu Baru Beli! {nama} Review",
                ]
                title = title_templates[(acct_num + i) % len(title_templates)]
                if len(title) > 100:
                    title = title[:97] + '...'

            # ── LONG-FORM DESCRIPTION (try Gemini first) ──
            rating = round(random.uniform(4.5, 4.9), 1)
            cta = random.choice(cta_variants)
            gemini_desc = _gemini_description(nama, category, harga, desc, shopee_url, 'long')
            if gemini_desc:
                description = gemini_desc
                if shopee_url not in description:
                    description = f"Beli di Shopee: {shopee_url}\n\n{description}"
                if not any(h in description for h in cat_hashtags[:3]):
                    description += f"\n\n{' '.join(cat_hashtags[:8])}"
            else:
                description = f"""Beli di Shopee: {shopee_url}

{nama}
Harga: {harga}

{desc}

Rating: {rating}/5

Video ini membahas secara lengkap tentang {nama}, termasuk kelebihan, kekurangan, dan apakah worth it untuk dibeli.

{cta}

Kategori: {cat_label}
Subscribe @{channel} untuk review produk {cat_label} lainnya!

{' '.join(cat_hashtags[:8])}"""

        else:
            # -- SHORTS TITLE (try Gemini first, fallback) --
            nama_short = nama[:25] if len(nama) > 25 else nama
            gemini_short_title = _gemini_title(nama, category, harga, 'short')
            if gemini_short_title and len(gemini_short_title) <= 50:
                title = gemini_short_title
            else:
                title_templates = [
                    f"{nama_short} | Review Jujur",
                    f"{nama_short} Worth It?",
                    f"Review {nama_short}",
                    f"Wajib Punya! {nama_short}",
                    f"Cobain {nama_short}",
                ]
                title = title_templates[(acct_num + i) % len(title_templates)]
                if len(title) > 50:
                    title = title[:47] + '...'

            # -- SHORTS DESCRIPTION --
            description = f"""Beli di Shopee: {shopee_url}

{nama}
Harga: {harga}
{desc}

{' '.join(cat_hashtags[:8])}"""

        metadata_results.append({
            'file': f"{today}_{produk_id}_v{variant_id}_{suffix}.mp4",
            'account_id': acct_id,
            'scheduled_time': scheduled_time,
            'title': title.strip(),
            'description': description.strip(),
            'hashtags': ' '.join(cat_hashtags[:8]),
            'video_type': video_type,
            'category': category,
        })

        # For Long slots, also create metadata for the auto-extracted Shorts
        if video_type == 'long':
            nama_short = nama[:25] if len(nama) > 25 else nama
            short_title_templates = [
                f"{nama_short} | Review Jujur",
                f"{nama_short} Worth It?",
                f"Review {nama_short}",
                f"Wajib Punya! {nama_short}",
            ]
            short_title = short_title_templates[(acct_num + i) % len(short_title_templates)]
            if len(short_title) > 50:
                short_title = short_title[:47] + '...'

            short_desc = f"""Beli di Shopee: {shopee_url}

{nama}
Harga: {harga}
{desc}

{' '.join(cat_hashtags[:8])}"""

            # Use shorts_scheduled_time if available (from batch_manager)
            shorts_sched = job.get('shorts_scheduled_time', scheduled_time)

            metadata_results.append({
                'file': f"{today}_{produk_id}_v{variant_id}_yt.mp4",
                'account_id': acct_id,
                'scheduled_time': shorts_sched,
                'title': short_title.strip(),
                'description': short_desc.strip(),
                'hashtags': ' '.join(cat_hashtags[:8]),
                'video_type': 'short',
                'category': category,
            })

    output_path = os.path.join(output_dir, "yt_metadata.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata_results, f, indent=2, ensure_ascii=False)

    long_count = sum(1 for m in metadata_results if m['video_type'] == 'long')
    short_count = sum(1 for m in metadata_results if m['video_type'] == 'short')
    print(f"YouTube metadata saved: {len(metadata_results)} entries "
          f"({long_count} long, {short_count} shorts) -> {output_path}")


if __name__ == "__main__":
    generate_metadata(
        "engine/queue/yt_queue.jsonl",
        "engine/data/produk.csv",
        "engine/state"
    )
