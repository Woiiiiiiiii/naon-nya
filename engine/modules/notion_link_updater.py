"""
notion_link_updater.py
Auto-update Notion pages with today's product affiliate links.

Structure on Notion:
  - 7 pages: YT_1, YT_2, YT_3, YT_4, YT_5, TT, FB
  - Each page has a linked product database
  - Products are added daily with affiliate links, then archived after 7 days

Environment variables:
  NOTION_API_KEY  — Internal Integration Token (secret_xxx)
  
Per-account database IDs (set in engine_config.yaml or env):
  NOTION_DB_YT_1, NOTION_DB_YT_2, ..., NOTION_DB_YT_5
  NOTION_DB_TT, NOTION_DB_FB

If ANY env var is missing, module skips gracefully.
"""
import json
import os
import sys
import datetime
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from engine.modules.category_router import get_category, get_label

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Mapping account_id → env var name for DB ID
ACCOUNT_DB_MAP = {
    'yt_1': 'NOTION_DB_YT_1',
    'yt_2': 'NOTION_DB_YT_2',
    'yt_3': 'NOTION_DB_YT_3',
    'yt_4': 'NOTION_DB_YT_4',
    'yt_5': 'NOTION_DB_YT_5',
    'tt_1': 'NOTION_DB_TT',
    'fb_1': 'NOTION_DB_FB',
}


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


def get_db_id(account_id):
    """Get Notion database ID for a specific account."""
    env_key = ACCOUNT_DB_MAP.get(account_id)
    if not env_key:
        return None
    return os.environ.get(env_key, '')


def archive_old_links(db_id, headers, days_old=7):
    """Uncheck status for links older than N days (checkbox → false)."""
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days_old)).strftime("%Y-%m-%d")

    query = {
        "filter": {
            "and": [
                {"property": "status", "checkbox": {"equals": True}},
                {"property": "post date", "date": {"before": cutoff}},
            ]
        }
    }

    try:
        resp = requests.post(
            f"{NOTION_API}/databases/{db_id}/query",
            headers=headers, json=query, timeout=30
        )
        if resp.status_code != 200:
            return 0

        pages = resp.json().get('results', [])
        archived = 0
        for page in pages:
            page_id = page['id']
            r = requests.patch(
                f"{NOTION_API}/pages/{page_id}",
                headers=headers,
                json={"properties": {"status": {"checkbox": False}}},
                timeout=15
            )
            if r.status_code == 200:
                archived += 1
        return archived
    except Exception:
        return 0


def add_product_to_db(db_id, headers, product_name, shopee_url, price,
                       account_id, category_label, date_str, video_type='long'):
    """Add a product link to a specific account's Notion database."""
    page_data = {
        "parent": {"database_id": db_id},
        "properties": {
            "name": {
                "title": [{"text": {"content": product_name[:100]}}]
            },
            "price": {
                "rich_text": [{"text": {"content": str(price)}}]
            },
            "account": {
                "select": {"name": account_id}
            },
            "category": {
                "select": {"name": category_label}
            },
            "link affiliate": {
                "url": shopee_url if shopee_url else None
            },
            "status": {
                "checkbox": True
            },
            "post date": {
                "date": {"start": date_str}
            },
            "video type": {
                "select": {"name": video_type}
            },
        }
    }

    try:
        resp = requests.post(
            f"{NOTION_API}/pages",
            headers=headers, json=page_data, timeout=15
        )
        return resp.status_code == 200
    except Exception:
        return False


def update_all_notion_pages(yt_metadata_path, tt_metadata_path=None, fb_metadata_path=None):
    """Update Notion pages for all accounts (YT_1-5, TT, FB)."""
    print("=== Notion Link Updater (Per-Account) ===")

    headers = get_headers()
    if not headers:
        print("  [SKIP] NOTION_API_KEY not set. Skipping Notion update.")
        print("  To enable: add NOTION_API_KEY to GitHub Secrets")
        return

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    total_added = 0
    total_archived = 0

    # ── YouTube Metadata → YT_1 through YT_5 ──
    if os.path.exists(yt_metadata_path):
        with open(yt_metadata_path, 'r', encoding='utf-8') as f:
            yt_meta = json.load(f)

        # Group by account
        by_account = {}
        for entry in yt_meta:
            acct = entry.get('account_id', 'unknown')
            if acct not in by_account:
                by_account[acct] = []
            by_account[acct].append(entry)

        for acct_id, entries in by_account.items():
            db_id = get_db_id(acct_id)
            if not db_id:
                print(f"  [{acct_id}] No NOTION_DB configured, skipping")
                continue

            cat_label = get_label(acct_id)
            print(f"  [{acct_id}] → {cat_label} (DB: {db_id[:8]}...)")

            # Archive old
            archived = archive_old_links(db_id, headers)
            if archived:
                print(f"    Archived {archived} old links")
            total_archived += archived

            # Add today's products (Long only, avoid duplication)
            seen = set()
            for entry in entries:
                vtype = entry.get('video_type', 'short')
                if vtype != 'long':
                    continue

                product_name = _extract_product_name(entry.get('title', ''))
                if product_name in seen:
                    continue
                seen.add(product_name)

                shopee_url = _extract_shopee_url(entry.get('description', ''))
                price = _extract_price(entry.get('description', ''))

                if add_product_to_db(db_id, headers, product_name, shopee_url,
                                     price, acct_id, cat_label, today, vtype):
                    print(f"    [OK] {product_name[:40]}")
                    total_added += 1
                else:
                    print(f"    [FAIL] {product_name[:40]}")

    # ── TikTok Metadata → TT ──
    tt_path = tt_metadata_path or "engine/state/tt_metadata.json"
    if os.path.exists(tt_path):
        db_id = get_db_id('tt_1')
        if db_id:
            with open(tt_path, 'r', encoding='utf-8') as f:
                tt_meta = json.load(f)

            print(f"\n  [tt_1] → TikTok (DB: {db_id[:8]}...)")
            archived = archive_old_links(db_id, headers)
            total_archived += archived

            seen = set()
            for entry in tt_meta:
                if entry.get('video_type') == 'short':
                    continue
                nama = entry.get('produk', '')
                if nama in seen:
                    continue
                seen.add(nama)

                shopee = entry.get('shopee_url', '')
                harga = entry.get('harga', '')

                if add_product_to_db(db_id, headers, nama, shopee, harga,
                                     'tt_1', 'TikTok', today, 'long'):
                    print(f"    [OK] {nama[:40]}")
                    total_added += 1

    # ── Facebook Metadata → FB ──
    fb_path = fb_metadata_path or "engine/state/fb_metadata.json"
    if os.path.exists(fb_path):
        db_id = get_db_id('fb_1')
        if db_id:
            with open(fb_path, 'r', encoding='utf-8') as f:
                fb_meta = json.load(f)

            print(f"\n  [fb_1] → Facebook (DB: {db_id[:8]}...)")
            archived = archive_old_links(db_id, headers)
            total_archived += archived

            seen = set()
            for entry in fb_meta:
                if entry.get('video_type') == 'short':
                    continue
                nama = entry.get('produk', '')
                if nama in seen:
                    continue
                seen.add(nama)

                shopee = entry.get('shopee_url', '')
                harga = entry.get('harga', '')

                if add_product_to_db(db_id, headers, nama, shopee, harga,
                                     'fb_1', 'Facebook', today, 'long'):
                    print(f"    [OK] {nama[:40]}")
                    total_added += 1

    print(f"\n=== Notion Complete: {total_added} added, {total_archived} archived ===")


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
