"""
batch_manager.py
Assigns products to accounts based on their CATEGORY.

Each YouTube account has a fixed category (from category_router.py):
  yt_1 = fashion, yt_2 = gadget, yt_3 = beauty, yt_4 = home, yt_5 = wellness

Each slot (pagi/siang/sore/malam), the batch manager:
1. Reads storyboard_queue.jsonl (products with category tags)
2. Assigns each account a product matching its category
3. Writes per-platform queues (yt_queue, tt_queue, fb_queue)
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


def manage_batch(storyboard_queue, yt_queue, tt_queue, fb_queue, state_file, config, slot_override=None):
    """
    Assigns products to accounts based on category.
    Each account gets a DIFFERENT product matching its category.
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

    print(f"=== Batch Manager v3.0 (Category-Based) ===")
    print(f"Slot: {slot}")

    if not os.path.exists(storyboard_queue):
        print(f"Error: {storyboard_queue} not found.")
        return

    # Load all jobs from storyboard queue
    all_jobs = []
    with open(storyboard_queue, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                all_jobs.append(json.loads(line))

    if not all_jobs:
        print("No jobs found in storyboard queue.")
        return

    # Group jobs by category
    jobs_by_category = {}
    for job in all_jobs:
        cat = job.get('category', 'unknown')
        if cat not in jobs_by_category:
            jobs_by_category[cat] = []
        jobs_by_category[cat].append(job)

    print(f"Products available: {', '.join(f'{k}={len(v)}' for k, v in jobs_by_category.items())}")

    # Get slot config
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    slot_config = schedule.get(slot, {})
    slot_range = slot_config.get('range', ['08:00', '10:00'])
    scheduled_time = _random_time_in_range(slot_range[0], slot_range[1])
    video_type = slot_config.get('video_type', 'long' if slot in ('pagi', 'sore') else 'short')

    # Shorts scheduled time for long slots
    shorts_scheduled_time = None
    shorts_target = slot_config.get('shorts_target', None)
    if video_type == 'long' and shorts_target:
        target_config = schedule.get(shorts_target, {})
        target_range = target_config.get('range', ['11:00', '14:00'])
        shorts_scheduled_time = _random_time_in_range(target_range[0], target_range[1])

    print(f"Time: {scheduled_time} | Type: {video_type}")

    # --- Use day+slot as seed for deterministic but rotating selection ---
    slot_idx = {"pagi": 0, "siang": 1, "sore": 2, "malam": 3}[slot]
    random.seed(f"{today_str}_{slot_idx}")

    # --- YOUTUBE: Each account gets a product from its OWN category ---
    yt_jobs = []
    for acct_num in range(1, yt_accounts + 1):
        acct_id = f"yt_{acct_num}"
        acct_config = YOUTUBE_CATEGORIES.get(acct_id, {})
        category = acct_config.get('category', 'fashion')

        # Find a product matching this account's category
        cat_jobs = jobs_by_category.get(category, [])

        # DEDUP: filter out products already used on this account
        cat_jobs = filter_queue(cat_jobs, acct_id)

        if not cat_jobs:
            print(f"  [WARN] No NEW products for {acct_id} (category={category}), ALL used up — skipping")
            continue

        print(f"    {acct_id}: {len(cat_jobs)} new products available in '{category}'")

        # Pick product — use unique seed per account+day+slot for variety
        random.seed(f"{today_str}_{slot_idx}_{acct_id}")
        selected_job = random.choice(cat_jobs).copy()

        selected_job['account_id'] = acct_id
        selected_job['variant_id'] = acct_num
        selected_job['platform'] = 'youtube'
        selected_job['slot'] = slot
        selected_job['scheduled_time'] = scheduled_time
        selected_job['video_type'] = video_type
        selected_job['date'] = today_str
        if shorts_scheduled_time:
            selected_job['shorts_scheduled_time'] = shorts_scheduled_time

        yt_jobs.append(selected_job)
        # DEDUP: mark product as used on this account
        mark_product_used(selected_job['produk_id'], acct_id,
                          selected_job.get('nama', ''), selected_job.get('shopee_url', ''))
        print(f"  {acct_id} ({category}): {selected_job['produk_id']} - {selected_job.get('nama', '?')[:40]}")

    # --- TIKTOK: Gets product from its alternating category ---
    tt_category = TIKTOK_ACCOUNT.get('category', 'fashion')
    tt_jobs = []
    tt_cat_jobs = filter_queue(jobs_by_category.get(tt_category, []), 'tt_1')
    if tt_cat_jobs:
        random.seed(f"{today_str}_{slot_idx}_tt_1")
        selected = random.choice(tt_cat_jobs).copy()
        selected['account_id'] = 'tt_1'
        selected['variant_id'] = 1
        selected['platform'] = 'tiktok'
        selected['slot'] = slot
        selected['scheduled_time'] = scheduled_time
        selected['video_type'] = video_type
        selected['date'] = today_str
        if shorts_scheduled_time:
            selected['shorts_scheduled_time'] = shorts_scheduled_time
        tt_jobs.append(selected)
        mark_product_used(selected['produk_id'], 'tt_1',
                          selected.get('nama', ''), selected.get('shopee_url', ''))
        print(f"  tt_1 ({tt_category}): {selected['produk_id']} - {selected.get('nama', '?')[:40]}")
    else:
        print(f"  [WARN] No products for tt_1 (category={tt_category})")

    # --- FACEBOOK: Gets product from its alternating category ---
    fb_category = FACEBOOK_ACCOUNT.get('category', 'home')
    fb_jobs = []
    fb_cat_jobs = filter_queue(jobs_by_category.get(fb_category, []), 'fb_1')
    if fb_cat_jobs:
        random.seed(f"{today_str}_{slot_idx}_fb_1")
        selected = random.choice(fb_cat_jobs).copy()
        selected['account_id'] = 'fb_1'
        selected['variant_id'] = 1
        selected['platform'] = 'facebook'
        selected['slot'] = slot
        selected['scheduled_time'] = scheduled_time
        selected['video_type'] = video_type
        selected['date'] = today_str
        if shorts_scheduled_time:
            selected['shorts_scheduled_time'] = shorts_scheduled_time
        fb_jobs.append(selected)
        mark_product_used(selected['produk_id'], 'fb_1',
                          selected.get('nama', ''), selected.get('shopee_url', ''))
        print(f"  fb_1 ({fb_category}): {selected['produk_id']} - {selected.get('nama', '?')[:40]}")
    else:
        print(f"  [WARN] No products for fb_1 (category={fb_category})")

    # Write to queues
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
    print(f"  YT: {len(yt_jobs)} videos (each different category)")
    print(f"  TT: {len(tt_jobs)} videos ({tt_category})")
    print(f"  FB: {len(fb_jobs)} videos ({fb_category})")
    print(f"  Queues written: {yt_queue}, {tt_queue}, {fb_queue}")


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
        "engine/queue/storyboard_queue.jsonl",
        "engine/queue/yt_queue.jsonl",
        "engine/queue/tt_queue.jsonl",
        "engine/queue/fb_queue.jsonl",
        "engine/state/video_state.csv",
        config,
        slot_override=args.slot
    )
