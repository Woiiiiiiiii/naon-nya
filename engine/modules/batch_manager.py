"""
batch_manager.py
Assigns products to accounts based on their CATEGORY.

Each YouTube account has a fixed category (from category_router.py):
  yt_1 = fashion, yt_2 = gadget, yt_3 = beauty, yt_4 = home, yt_5 = wellness

OPTIMIZED: Reads directly from produk.csv (not storyboard_queue.jsonl).
Picks 1 product per category, validates image inline, retries on QC failure.
Only selected products (5-7) get processed — NOT all 270.
"""
import json
import os
import pandas as pd
import sys
import random
import datetime

sys.path.insert(0, os.path.dirname(__file__))
try:
    from category_router import (
        YOUTUBE_CATEGORIES, TIKTOK_ACCOUNT, FACEBOOK_ACCOUNT, CATEGORY_KEYWORDS
    )
except ImportError:
    YOUTUBE_CATEGORIES = {
        'yt_1': {'category': 'fashion'}, 'yt_2': {'category': 'gadget'},
        'yt_3': {'category': 'beauty'}, 'yt_4': {'category': 'home'},
        'yt_5': {'category': 'wellness'},
    }
    TIKTOK_ACCOUNT = {'account_id': 'tt_1', 'category': 'fashion'}
    FACEBOOK_ACCOUNT = {'account_id': 'fb_1', 'category': 'home'}

try:
    from dedup_tracker import filter_queue, mark_product_used
except ImportError:
    def filter_queue(jobs, account_id): return jobs
    def mark_product_used(product_id, account_id, product_name='', url=''): pass

try:
    from product_validator import validate_product_image
except ImportError:
    def validate_product_image(produk_id, images_dir='engine/data/images'):
        return 'pass', None


# Masalah templates (inline — no need for separate extract_masalah step)
MASALAH_TEMPLATES = [
    "Sering bingung cari {nama} yang berkualitas tapi harga terjangkau?",
    "Capek pakai {nama} murahan yang cepat rusak?",
    "Udah coba berbagai {nama} tapi belum puas?",
    "Butuh {nama} yang tahan lama dan gak mahal?",
    "Males ribet? {nama} ini bikin hidupmu lebih simpel!",
    "Jangan buang uang buat {nama} abal-abal, mending yang ini!",
]

# Hook/CTA templates (inline)
HOOK_TEMPLATES = [
    "Kamu masih pakai yang biasa?",
    "STOP! Jangan scroll dulu!",
    "Wajib tau sebelum beli {nama}!",
    "Ini yang lagi viral!",
    "Review jujur {nama}!",
]
CTA_TEMPLATES = [
    "Klik link di bio untuk beli!",
    "Cek harga spesial di link bio!",
    "Stok terbatas! Grab sekarang!",
    "Link pembelian ada di bio!",
]


def _select_and_validate_product(products_df, category, account_id, rng, images_dir='engine/data/images'):
    """Pick 1 product from category, validate image.
    If QC fails, try next product. Returns (product_dict, image_path) or (None, None)."""
    cat_products = products_df[products_df['category'] == category].copy()
    if cat_products.empty:
        print(f"    [WARN] No products in category '{category}'")
        return None, None

    # Convert to list of dicts for dedup filter
    cat_jobs = cat_products.to_dict('records')
    cat_jobs = filter_queue(cat_jobs, account_id)

    if not cat_jobs:
        print(f"    [WARN] No NEW products for {account_id} (category={category}), ALL used up")
        return None, None

    # Shuffle for variety
    rng.shuffle(cat_jobs)

    # Try each product until one passes image QC
    for product in cat_jobs:
        pid = product['produk_id']
        status, valid_path = validate_product_image(pid, images_dir)

        if status == 'hard_reject':
            print(f"    [{account_id}] {pid} image REJECTED, trying next...")
            continue

        # pass or soft_reject = OK to use
        print(f"    [{account_id}] {pid} image OK (status={status})")
        return product, valid_path

    print(f"    [WARN] All products in '{category}' failed image QC for {account_id}")
    return None, None


def _make_storyboard_entry(product, rng):
    """Create a storyboard entry for a selected product."""
    nama = str(product.get('nama', ''))

    template = rng.choice(MASALAH_TEMPLATES)
    masalah = template.format(nama=nama[:30].lower())

    hook_template = rng.choice(HOOK_TEMPLATES)
    hook = hook_template.format(nama=nama[:20]) if '{nama}' in hook_template else hook_template
    cta = rng.choice(CTA_TEMPLATES)

    return {
        "produk_id": product['produk_id'],
        "nama": nama,
        "category": product.get('category', 'fashion'),
        "harga": str(product.get('price', product.get('harga', ''))),
        "shopee_url": str(product.get('shopee_url', '')),
        "image_url": str(product.get('image_url', '')),
        "hook": hook,
        "masalah": masalah,
        "solusi": f"Pakai {nama[:30]} aja!",
        "cta": cta,
        "scene_order": ["hook", "masalah", "solusi", "cta"],
    }


def manage_batch(produk_csv, yt_queue, tt_queue, fb_queue, state_file, config, slot_override=None):
    """
    Assigns products to accounts based on category.
    READS DIRECTLY from produk.csv — picks 1 per category, validates image inline.
    Only 5-7 products processed per run (not 270).
    """
    yt_accounts = config.get('accounts', {}).get('youtube', 5)
    schedule = config.get('schedule', {}).get('slots', {})

    # Determine slot
    if slot_override:
        slot = slot_override
    else:
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12:
            slot = "pagi"
        elif 12 <= hour < 15:
            slot = "siang"
        elif 15 <= hour < 18:
            slot = "sore"
        else:
            slot = "malam"

    print(f"=== Batch Manager v4.0 (Direct CSV + Inline QC) ===")
    print(f"Slot: {slot}")

    # Read produk.csv directly
    if not os.path.exists(produk_csv):
        print(f"Error: {produk_csv} not found.")
        return

    products_df = pd.read_csv(produk_csv)
    if 'category' not in products_df.columns:
        products_df['category'] = 'fashion'

    print(f"Stock: {len(products_df)} products")
    cat_counts = products_df['category'].value_counts()
    for cat, cnt in cat_counts.items():
        print(f"  {cat}: {cnt} products")

    # Slot config
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    slot_config = schedule.get(slot, {})
    slot_range = slot_config.get('range', ['08:00', '10:00'])
    scheduled_time = _random_time_in_range(slot_range[0], slot_range[1])
    video_type = slot_config.get('video_type', 'long' if slot in ('pagi', 'sore') else 'short')

    shorts_scheduled_time = None
    shorts_target = slot_config.get('shorts_target', None)
    if video_type == 'long' and shorts_target:
        target_config = schedule.get(shorts_target, {})
        target_range = target_config.get('range', ['11:00', '14:00'])
        shorts_scheduled_time = _random_time_in_range(target_range[0], target_range[1])

    print(f"Time: {scheduled_time} | Type: {video_type}")

    slot_idx = {"pagi": 0, "siang": 1, "sore": 2, "malam": 3}[slot]
    storyboard_entries = []

    # --- YOUTUBE: Each account gets 1 product from its category ---
    yt_jobs = []
    for acct_num in range(1, yt_accounts + 1):
        acct_id = f"yt_{acct_num}"
        acct_config = YOUTUBE_CATEGORIES.get(acct_id, {})
        category = acct_config.get('category', 'fashion')

        rng = random.Random(f"{today_str}_{slot_idx}_{acct_id}")
        product, valid_path = _select_and_validate_product(products_df, category, acct_id, rng)

        if product is None:
            print(f"  [SKIP] {acct_id}: no valid product for '{category}'")
            continue

        sb_entry = _make_storyboard_entry(product, rng)
        storyboard_entries.append(sb_entry)

        job = sb_entry.copy()
        job['account_id'] = acct_id
        job['variant_id'] = acct_num
        job['platform'] = 'youtube'
        job['slot'] = slot
        job['scheduled_time'] = scheduled_time
        job['video_type'] = video_type
        job['date'] = today_str
        if shorts_scheduled_time:
            job['shorts_scheduled_time'] = shorts_scheduled_time

        yt_jobs.append(job)
        mark_product_used(product['produk_id'], acct_id,
                          product.get('nama', ''), product.get('shopee_url', ''))
        print(f"  {acct_id} ({category}): {product['produk_id']} - {str(product.get('nama', '?'))[:40]}")

    # --- TIKTOK ---
    tt_category = TIKTOK_ACCOUNT.get('category', 'fashion')
    tt_jobs = []
    rng_tt = random.Random(f"{today_str}_{slot_idx}_tt_1")
    product, _ = _select_and_validate_product(products_df, tt_category, 'tt_1', rng_tt)
    if product is not None:
        sb_entry = _make_storyboard_entry(product, rng_tt)
        storyboard_entries.append(sb_entry)
        job = sb_entry.copy()
        job['account_id'] = 'tt_1'
        job['variant_id'] = 1
        job['platform'] = 'tiktok'
        job['slot'] = slot
        job['scheduled_time'] = scheduled_time
        job['video_type'] = video_type
        job['date'] = today_str
        if shorts_scheduled_time:
            job['shorts_scheduled_time'] = shorts_scheduled_time
        tt_jobs.append(job)
        mark_product_used(product['produk_id'], 'tt_1',
                          product.get('nama', ''), product.get('shopee_url', ''))
        print(f"  tt_1 ({tt_category}): {product['produk_id']} - {str(product.get('nama', '?'))[:40]}")
    else:
        print(f"  [WARN] No valid product for tt_1 (category={tt_category})")

    # --- FACEBOOK ---
    fb_category = FACEBOOK_ACCOUNT.get('category', 'home')
    fb_jobs = []
    rng_fb = random.Random(f"{today_str}_{slot_idx}_fb_1")
    product, _ = _select_and_validate_product(products_df, fb_category, 'fb_1', rng_fb)
    if product is not None:
        sb_entry = _make_storyboard_entry(product, rng_fb)
        storyboard_entries.append(sb_entry)
        job = sb_entry.copy()
        job['account_id'] = 'fb_1'
        job['variant_id'] = 1
        job['platform'] = 'facebook'
        job['slot'] = slot
        job['scheduled_time'] = scheduled_time
        job['video_type'] = video_type
        job['date'] = today_str
        if shorts_scheduled_time:
            job['shorts_scheduled_time'] = shorts_scheduled_time
        fb_jobs.append(job)
        mark_product_used(product['produk_id'], 'fb_1',
                          product.get('nama', ''), product.get('shopee_url', ''))
        print(f"  fb_1 ({fb_category}): {product['produk_id']} - {str(product.get('nama', '?'))[:40]}")
    else:
        print(f"  [WARN] No valid product for fb_1 (category={fb_category})")

    # Write storyboard for selected products ONLY
    sb_path = os.path.join(os.path.dirname(yt_queue), 'storyboard_queue.jsonl')
    os.makedirs(os.path.dirname(sb_path), exist_ok=True)
    with open(sb_path, 'w', encoding='utf-8') as f:
        for entry in storyboard_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    print(f"\n  Storyboard: {len(storyboard_entries)} entries (selected only)")

    # Write platform queues
    os.makedirs(os.path.dirname(yt_queue), exist_ok=True)
    with open(yt_queue, 'w', encoding='utf-8') as f:
        for job in yt_jobs:
            f.write(json.dumps(job, ensure_ascii=False) + '\n')

    with open(tt_queue, 'w', encoding='utf-8') as f:
        for job in tt_jobs:
            f.write(json.dumps(job, ensure_ascii=False) + '\n')

    with open(fb_queue, 'w', encoding='utf-8') as f:
        for job in fb_jobs:
            f.write(json.dumps(job, ensure_ascii=False) + '\n')

    # Update state
    state_data = []
    for job in yt_jobs + tt_jobs + fb_jobs:
        state_data.append({
            'produk_id': job['produk_id'],
            'account_id': job['account_id'],
            'category': job.get('category', ''),
            'variant_id': job['variant_id'],
            'platform': job['platform'],
            'slot': slot,
            'scheduled_time': scheduled_time,
            'status': 'queued',
            'timestamp': datetime.datetime.now().isoformat()
        })

    state_df = pd.DataFrame(state_data)
    if os.path.exists(state_file):
        state_df.to_csv(state_file, mode='a', header=False, index=False)
    else:
        state_df.to_csv(state_file, index=False)

    print(f"\n=== Batch Summary ===")
    print(f"  YT: {len(yt_jobs)} videos")
    print(f"  TT: {len(tt_jobs)} videos")
    print(f"  FB: {len(fb_jobs)} videos")
    print(f"  Total products processed: {len(storyboard_entries)} (NOT {len(products_df)})")


def _random_time_in_range(start_str, end_str):
    """Generate random HH:MM time within a range."""
    sh, sm = map(int, start_str.split(':'))
    eh, em = map(int, end_str.split(':'))
    start_min = sh * 60 + sm
    end_min = eh * 60 + em
    rand_min = random.randint(start_min, end_min)
    return f"{rand_min // 60:02d}:{rand_min % 60:02d}"


if __name__ == "__main__":
    import yaml
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", choices=["pagi", "siang", "sore", "malam"], help="Force specific slot")
    args = parser.parse_args()

    with open("engine/config/engine_config.yaml", 'r') as f:
        config = yaml.safe_load(f)

    manage_batch(
        "engine/data/produk.csv",
        "engine/queue/yt_queue.jsonl",
        "engine/queue/tt_queue.jsonl",
        "engine/queue/fb_queue.jsonl",
        "engine/state/video_state.csv",
        config,
        slot_override=args.slot
    )
