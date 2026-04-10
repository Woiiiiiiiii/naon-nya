"""
notion_link_updater.py
Auto-update Notion database with today's product affiliate links.

Structure on Notion:
  - 1 database "Products" shared by ALL accounts (YT_1-5, TT, FB)
  - "Account" column filters which account each row belongs to
  - Products are added daily, old ones (>7 days) get status unchecked

Environment variables:
  NOTION_API_KEY  — Internal Integration Token (ntn_xxx)
  NOTION_DB_ID    — Single database ID for all accounts

If env vars missing, module skips gracefully (no error).
"""
import json
import os
import sys
import datetime
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from category_router import get_category, get_label

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def get_headers():
    """Get Notion API headers using internal integration token."""
    token = os.environ.get('NOTION_API_KEY', '')
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def get_db_id():
    """Get the single Notion database ID."""
    return os.environ.get('NOTION_DB_ID', '')


def archive_old_links(db_id, headers, days_old=7):
    """Uncheck status for links older than N days (checkbox → false)."""
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days_old)).strftime("%Y-%m-%d")

    query = {
        "filter": {
            "and": [
                {"property": "Status", "checkbox": {"equals": True}},
                {"property": "Post Date", "date": {"before": cutoff}},
            ]
        }
    }

    try:
        resp = requests.post(
            f"{NOTION_API}/databases/{db_id}/query",
            headers=headers, json=query, timeout=30
        )
        if resp.status_code != 200:
            print(f"    [NOTION] Archive query failed: {resp.status_code}")
            return 0

        pages = resp.json().get('results', [])
        archived = 0
        for page in pages:
            page_id = page['id']
            r = requests.patch(
                f"{NOTION_API}/pages/{page_id}",
                headers=headers,
                json={"properties": {"Status": {"checkbox": False}}},
                timeout=15
            )
            if r.status_code == 200:
                archived += 1
        return archived
    except Exception as e:
        print(f"    [NOTION] Archive error: {e}")
        return 0


def _check_duplicate(db_id, headers, product_name, account_id, date_str):
    """Check if product already exists in DB for this account + date."""
    query = {
        "filter": {
            "and": [
                {"property": "Account", "select": {"equals": account_id}},
                {"property": "Post Date", "date": {"equals": date_str}},
            ]
        },
        "page_size": 50,
    }
    try:
        resp = requests.post(
            f"{NOTION_API}/databases/{db_id}/query",
            headers=headers, json=query, timeout=15
        )
        if resp.status_code == 200:
            for page in resp.json().get('results', []):
                title_prop = page.get('properties', {}).get('Name', {})
                titles = title_prop.get('title', [])
                if titles:
                    existing = titles[0].get('text', {}).get('content', '')
                    if existing == product_name[:100]:
                        return True
    except Exception:
        pass
    return False


def add_product_to_db(db_id, headers, product_name, shopee_url, price,
                       account_id, category_label, date_str, video_type='long'):
    """Add a product link to the single Notion database."""
    # Skip duplicates
    if _check_duplicate(db_id, headers, product_name, account_id, date_str):
        print(f"    [SKIP] Already exists: {product_name[:30]} ({account_id})")
        return False

    page_data = {
        "parent": {"database_id": db_id},
        "properties": {
            "Name": {
                "title": [{"text": {"content": product_name[:100]}}]
            },
            "Price": {
                "number": _parse_price(price)
            },
            "Account": {
                "select": {"name": account_id}
            },
            "Category": {
                "select": {"name": category_label}
            },
            "Link Affiliate": {
                "url": shopee_url if shopee_url else None
            },
            "Status": {
                "checkbox": True
            },
            "Post Date": {
                "date": {"start": date_str}
            },
            "Video Type": {
                "select": {"name": video_type}
            },
        }
    }

    try:
        resp = requests.post(
            f"{NOTION_API}/pages",
            headers=headers, json=page_data, timeout=15
        )
        if resp.status_code == 200:
            return True
        else:
            print(f"    [NOTION] Add failed ({resp.status_code}): {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"    [NOTION] Add error: {e}")
        return False


def _parse_price(price_str):
    """Parse price string to number. Returns 0 if unparseable."""
    if not price_str:
        return 0
    try:
        cleaned = str(price_str).replace('Rp', '').replace('Rp.', '')
        cleaned = cleaned.replace('.', '').replace(',', '').strip()
        return int(cleaned)
    except (ValueError, TypeError):
        return 0


def update_all_notion_pages(yt_metadata_path, tt_metadata_path=None, fb_metadata_path=None):
    """Update single Notion database for all accounts (YT_1-5, TT, FB)."""
    print("=== Notion Link Updater (Single Database) ===")

    headers = get_headers()
    if not headers:
        print("  [SKIP] NOTION_API_KEY not set. Skipping Notion update.")
        print("  To enable: add NOTION_API_KEY to GitHub Secrets")
        return

    db_id = get_db_id()
    if not db_id:
        print("  [SKIP] NOTION_DB_ID not set. Skipping Notion update.")
        print("  To enable: add NOTION_DB_ID to GitHub Secrets")
        return

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    total_added = 0

    # Archive old entries (>7 days)
    archived = archive_old_links(db_id, headers)
    if archived:
        print(f"  Archived {archived} old links (>7 days)")

    # ── YouTube Metadata → YT_1 through YT_5 ──
    if os.path.exists(yt_metadata_path):
        with open(yt_metadata_path, 'r', encoding='utf-8') as f:
            yt_meta = json.load(f)

        for entry in yt_meta:
            vtype = entry.get('video_type', 'short')
            if vtype != 'long':
                continue  # Only long-form gets Notion entry

            acct_id = entry.get('account_id', 'unknown')
            cat_label = get_label(acct_id)
            product_name = _extract_product_name(entry.get('title', ''))
            shopee_url = _extract_shopee_url(entry.get('description', ''))
            price = _extract_price(entry.get('description', ''))

            if add_product_to_db(db_id, headers, product_name, shopee_url,
                                  price, acct_id, cat_label, today, vtype):
                print(f"    [OK] {acct_id}: {product_name[:40]}")
                total_added += 1

    # ── TikTok Metadata → tt_1 ──
    tt_path = tt_metadata_path or "engine/state/tt_metadata.json"
    if os.path.exists(tt_path):
        with open(tt_path, 'r', encoding='utf-8') as f:
            tt_meta = json.load(f)

        seen = set()
        for entry in tt_meta:
            if entry.get('video_type') == 'short':
                continue
            nama = entry.get('produk', '')
            if nama in seen:
                continue
            seen.add(nama)

            acct_id = entry.get('account_id', 'tt_1')
            shopee = entry.get('shopee_url', '')
            harga = entry.get('harga', '')

            if add_product_to_db(db_id, headers, nama, shopee, harga,
                                  acct_id, 'TikTok', today, 'long'):
                print(f"    [OK] {acct_id}: {nama[:40]}")
                total_added += 1

    # ── Facebook Metadata → fb_1 ──
    fb_path = fb_metadata_path or "engine/state/fb_metadata.json"
    if os.path.exists(fb_path):
        with open(fb_path, 'r', encoding='utf-8') as f:
            fb_meta = json.load(f)

        seen = set()
        for entry in fb_meta:
            if entry.get('video_type') == 'short':
                continue
            nama = entry.get('produk', '')
            if nama in seen:
                continue
            seen.add(nama)

            acct_id = entry.get('account_id', 'fb_1')
            shopee = entry.get('shopee_url', '')
            harga = entry.get('harga', '')

            if add_product_to_db(db_id, headers, nama, shopee, harga,
                                  acct_id, 'Facebook', today, 'long'):
                print(f"    [OK] {acct_id}: {nama[:40]}")
                total_added += 1

    print(f"\n=== Notion Complete: {total_added} added, {archived} archived ===")


def _extract_product_name(title):
    """Extract clean product name from video title."""
    name = title.split('|')[0].split('—')[0].split(':')[-1].strip()
    name = ''.join(c for c in name if ord(c) < 0x10000
                   and not (0x2600 <= ord(c) <= 0x27BF
                            or 0x1F300 <= ord(c) <= 0x1F9FF))
    return name.strip()


def _extract_shopee_url(desc):
    """Extract Shopee URL from description."""
    for line in desc.split('\n'):
        if 'shopee.co.id' in line:
            url = line.replace('🛒', '').replace('Beli di Shopee:', '').strip()
            return url
    return ''


def _extract_price(desc):
    """Extract price from description."""
    for line in desc.split('\n'):
        if '💰' in line:
            return line.replace('💰', '').replace('Harga:', '').strip()
    return ''


if __name__ == "__main__":
    update_all_notion_pages("engine/state/yt_metadata.json")
