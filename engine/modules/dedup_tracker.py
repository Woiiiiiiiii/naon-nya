"""
dedup_tracker.py
Product deduplication system — prevents same product from appearing
on the same account/platform within 30 days.
"""
import os
import json
import datetime

STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')
DEDUP_FILE = os.path.join(STATE_DIR, 'used_products.json')
EXPIRY_DAYS = 9999  # PERMANENT — produk yang sudah diposting TIDAK BOLEH dipakai lagi SELAMANYA


def _load():
    """Load used products tracking data."""
    if os.path.exists(DEDUP_FILE):
        with open(DEDUP_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save(data):
    """Save used products tracking data."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(DEDUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_product_used(product_id, account_id):
    """Check if a product was used on this account within 30 days."""
    data = _load()
    acct_data = data.get(account_id, {})
    entry = acct_data.get(str(product_id))

    if not entry:
        return False
    # PERMANENT: kalau sudah pernah dipakai = TIDAK BOLEH lagi, SELAMANYA
    return True


def mark_product_used(product_id, account_id, product_name='', url=''):
    """Mark a product as used on this account."""
    data = _load()
    if account_id not in data:
        data[account_id] = {}

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    expiry = (datetime.datetime.now() + datetime.timedelta(days=EXPIRY_DAYS)).strftime('%Y-%m-%d')

    data[account_id][str(product_id)] = {
        'nama': product_name,
        'url': url,
        'tanggal_dipakai': today,
        'expired_date': expiry,
    }

    _save(data)


def cleanup_expired():
    """Remove expired entries to keep the file clean."""
    data = _load()
    today = datetime.datetime.now()
    cleaned = 0

    # PERMANENT dedup — tidak pernah dihapus
    total_entries = sum(len(v) for v in data.values())
    print(f"  [DEDUP] {total_entries} produk sudah pernah dipakai (permanent, tidak akan diulang)")


def filter_queue(jobs, account_id):
    """Filter a list of jobs, removing already-used products for this account.
    Returns filtered jobs list.
    """
    cleanup_expired()
    filtered = []
    skipped = 0

    for job in jobs:
        produk_id = job.get('produk_id', '')
        if is_product_used(produk_id, account_id):
            skipped += 1
            continue
        filtered.append(job)

    if skipped > 0:
        print(f"  [DEDUP] Skipped {skipped} already-used products for {account_id}")

    return filtered


if __name__ == "__main__":
    os.makedirs(STATE_DIR, exist_ok=True)
    print("Dedup Tracker ready")
    # Initialize empty state
    if not os.path.exists(DEDUP_FILE):
        _save({})
        print(f"  Created {DEDUP_FILE}")
