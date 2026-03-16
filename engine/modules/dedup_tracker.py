"""
dedup_tracker.py
Product deduplication system — prevents same product from appearing
across ANY account/platform EVER (permanent, no expiry).

Also cleans up used product images and bank entries to save storage.
"""
import os
import json
import datetime
import shutil

STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')
DEDUP_FILE = os.path.join(STATE_DIR, 'used_products.json')
BANK_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'product_bank')
IMAGES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'images')


def _load():
    """Load used products tracking data."""
    if os.path.exists(DEDUP_FILE):
        try:
            with open(DEDUP_FILE, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            # Corrupted file — start fresh
            return {}
    return {}


def _save(data):
    """Save used products tracking data."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(DEDUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_product_used(product_id, account_id=None):
    """Check if a product was EVER used on ANY account (global dedup).

    If account_id is provided, checks that specific account first,
    then checks ALL other accounts too — product must be unique
    across the entire system.
    """
    data = _load()

    # Check ALL accounts — global dedup
    for acct_id, acct_data in data.items():
        if str(product_id) in acct_data:
            return True

    return False


def mark_product_used(product_id, account_id, product_name='', url=''):
    """Mark a product as used on this account (permanent, never reused)."""
    data = _load()
    if account_id not in data:
        data[account_id] = {}

    today = datetime.datetime.now().strftime('%Y-%m-%d')

    data[account_id][str(product_id)] = {
        'nama': product_name,
        'url': url,
        'tanggal_dipakai': today,
    }

    _save(data)


def cleanup_used_images():
    """Delete images and bank entries for products that have been used.

    This frees up storage — used products will never be needed again
    since they can't be reused (permanent dedup).
    """
    data = _load()
    deleted_images = 0
    deleted_bank = 0

    # Collect all used product IDs across all accounts
    all_used_ids = set()
    for acct_data in data.values():
        all_used_ids.update(acct_data.keys())

    if not all_used_ids:
        return

    # Clean up images directory
    if os.path.exists(IMAGES_DIR):
        for filename in os.listdir(IMAGES_DIR):
            # Match produk_id from filename (e.g., p12345.jpg, p12345.png, p12345_2.jpg)
            base = os.path.splitext(filename)[0]
            # Remove suffix like _2, _3
            pid = base.split('_')[0] if '_' in base else base
            if pid in all_used_ids:
                try:
                    filepath = os.path.join(IMAGES_DIR, filename)
                    os.remove(filepath)
                    deleted_images += 1
                except Exception:
                    pass
            # Also remove .placeholder marker files
            marker = os.path.join(IMAGES_DIR, filename + '.placeholder')
            if os.path.exists(marker):
                try:
                    os.remove(marker)
                except Exception:
                    pass

    # Clean up product bank entries
    if os.path.exists(BANK_DIR):
        for category in os.listdir(BANK_DIR):
            cat_dir = os.path.join(BANK_DIR, category)
            if not os.path.isdir(cat_dir):
                continue
            for pid_dir in os.listdir(cat_dir):
                if pid_dir in all_used_ids:
                    try:
                        shutil.rmtree(os.path.join(cat_dir, pid_dir))
                        deleted_bank += 1
                    except Exception:
                        pass

    if deleted_images or deleted_bank:
        print(f"  [CLEANUP] Deleted {deleted_images} images, {deleted_bank} bank entries (already used)")


def filter_queue(jobs, account_id):
    """Filter a list of jobs, removing already-used products (global).
    Returns filtered jobs list.
    """
    filtered = []
    skipped = 0

    for job in jobs:
        produk_id = job.get('produk_id', '')
        if is_product_used(produk_id):
            skipped += 1
            continue
        filtered.append(job)

    if skipped > 0:
        print(f"  [DEDUP] Skipped {skipped} already-used products (global, permanent)")

    return filtered


def get_stats():
    """Get dedup statistics."""
    data = _load()
    total = sum(len(v) for v in data.values())
    accounts = len(data)
    return {'total_used': total, 'accounts': accounts}


if __name__ == "__main__":
    os.makedirs(STATE_DIR, exist_ok=True)
    stats = get_stats()
    print(f"Dedup Tracker: {stats['total_used']} products used across {stats['accounts']} accounts")
    if not os.path.exists(DEDUP_FILE):
        _save({})
        print(f"  Created {DEDUP_FILE}")
