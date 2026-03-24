"""
shopee_collector_v2.py
Simple 2-API product collector following user's 9-step approach.

Flow:
  API 1: affiliate.shopee.co.id/api/v3/offer/product/list
         → Get product list with item_id + shop_id
  API 2: shopee.co.id/api/v4/item/get?itemid=XXX&shopid=XXX
         → Get product detail (name, price, images)

Only needs: SHOPEE_AFFILIATE_COOKIES (satu secret saja)
Run locally: python shopee_collector_v2.py
"""

import os
import sys
import json
import time
import random
import hashlib
import requests
from urllib.parse import urlencode, unquote

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
AFFILIATE_BASE = 'https://affiliate.shopee.co.id'
SHOPEE_BASE = 'https://shopee.co.id'
BANK_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'product_bank')
TARGET_PER_CATEGORY = 25
CATEGORIES = ['fashion', 'gadget', 'beauty', 'home', 'wellness']

# Category keywords for affiliate product search
CATEGORY_KEYWORDS = {
    'fashion': ['tas', 'sepatu', 'jam tangan', 'kaos', 'dompet', 'kacamata',
                'gelang', 'hoodie', 'jaket', 'dress', 'celana'],
    'gadget': ['earphone', 'powerbank', 'charger', 'keyboard', 'mouse',
               'speaker', 'smartwatch', 'tripod', 'webcam', 'headphone'],
    'beauty': ['serum', 'sunscreen', 'moisturizer', 'lip tint', 'cushion',
               'skincare', 'makeup', 'mascara', 'foundation', 'toner'],
    'home': ['rak', 'lampu', 'organizer', 'vacuum', 'dapur',
             'bantal', 'dispenser', 'timbangan', 'gorden', 'sapu'],
    'wellness': ['yoga', 'botol minum', 'gym', 'vitamin', 'massage',
                 'resistance band', 'matras', 'shaker', 'dumbell', 'termos'],
}


# ═══════════════════════════════════════════════════════════════════
#  STEP 1-2: BUILD REQUEST FROM COOKIES
# ═══════════════════════════════════════════════════════════════════
def _build_cookies_and_headers():
    """Build cookie string + headers from SHOPEE_AFFILIATE_COOKIES.
    Extracts security tokens directly from cookie values.
    Returns: (cookie_string, headers_dict)
    """
    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not cookies_raw:
        print("  ❌ SHOPEE_AFFILIATE_COOKIES not set!")
        return '', {}

    try:
        cookies = json.loads(cookies_raw)
    except Exception as e:
        print(f"  ❌ Failed to parse cookies: {e}")
        return '', {}

    # Build cookie string
    if isinstance(cookies, list):
        cookie_str = '; '.join([
            f"{c.get('name', '')}={c.get('value', '')}"
            for c in cookies if c.get('name')
        ])
    elif isinstance(cookies, dict):
        cookie_str = '; '.join([f'{k}={v}' for k, v in cookies.items()])
    else:
        return '', {}

    # Extract special values from cookies
    csrftoken = ''
    sz_token = ''
    if isinstance(cookies, list):
        for c in cookies:
            if c.get('name') == 'csrftoken':
                csrftoken = c.get('value', '')
            if c.get('name') == 'shopee_webUnique_ccd':
                sz_token = unquote(c.get('value', ''))

    # Headers matching exact Chrome browser request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,id;q=0.7',
        'Referer': f'{AFFILIATE_BASE}/offer/brand_offer',
        'Origin': AFFILIATE_BASE,
        'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'affiliate-program-type': '1',
        'x-sz-sdk-version': '1.12.21',
        'Cookie': cookie_str,
    }

    if csrftoken:
        headers['x-csrftoken'] = csrftoken
    if sz_token:
        headers['af-ac-enc-sz-token'] = sz_token

    return cookie_str, headers


# ═══════════════════════════════════════════════════════════════════
#  STEP 3-5: GET PRODUCT LIST FROM AFFILIATE API (with pagination)
# ═══════════════════════════════════════════════════════════════════
def get_affiliate_products(headers, target=25, category_filter=None):
    """STEP 3-5: Fetch product list from affiliate API with pagination.
    
    Returns list of dicts with: item_id, shop_id, product_link, commission
    """
    url = f"{AFFILIATE_BASE}/api/v3/offer/product/list"
    products = []
    page = 0
    page_size = 20
    max_pages = 10  # Safety limit

    while len(products) < target and page < max_pages:
        params = {
            'list_type': 5,
            'sort_type': 5,
            'page_offset': page * page_size,
            'page_limit': page_size,
            'client_type': 1,
        }

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            print(f"    [Page {page+1}] HTTP {resp.status_code}")

            if resp.status_code != 200:
                print(f"    Response: {resp.text[:200]}")
                break

            data = resp.json()
            if data.get('code') != 0:
                err = data.get('error', data.get('code', '?'))
                print(f"    API error: {err}")
                break

            items = data.get('data', {}).get('list', [])
            total = data.get('data', {}).get('total_count', 0)

            if not items:
                print(f"    No more items (total={total})")
                break

            # Debug: show structure on first page
            if page == 0:
                print(f"    Total available: {total}")
                print(f"    Item keys: {list(items[0].keys())}")

            for item in items:
                if len(products) >= target:
                    break
                products.append(item)

            print(f"    Got {len(items)} items (total collected: {len(products)})")
            page += 1
            time.sleep(random.uniform(0.5, 1.5))

        except Exception as e:
            print(f"    Error: {e}")
            break

    return products


# ═══════════════════════════════════════════════════════════════════
#  STEP 6: EXTRACT itemid & shopid FROM RESPONSE
# ═══════════════════════════════════════════════════════════════════
def extract_product_ids(item):
    """STEP 6: Extract itemid + shopid from affiliate product response.
    
    Tries multiple locations:
    1. Direct fields: item_id, shop_id
    2. Nested in batch_item_for_item_card_full: itemid, shopid
    3. Parse from product_link URL
    """
    item_id = item.get('item_id', 0)
    shop_id = item.get('shop_id', 0)

    # Try nested item card
    if not item_id or not shop_id:
        nested = item.get('batch_item_for_item_card_full', {})
        if isinstance(nested, dict):
            item_id = item_id or nested.get('itemid', 0)
            shop_id = shop_id or nested.get('shopid', 0)

    # Try parsing from product_link
    if not item_id or not shop_id:
        link = item.get('product_link', item.get('long_link', ''))
        if '/product/' in link:
            parts = link.split('/product/')[-1].split('?')[0].split('/')
            if len(parts) >= 2:
                try:
                    shop_id = shop_id or int(parts[0])
                    item_id = item_id or int(parts[1])
                except ValueError:
                    pass

    return item_id, shop_id


# ═══════════════════════════════════════════════════════════════════
#  STEP 7: GET PRODUCT DETAIL (NAME, PRICE, IMAGES)
# ═══════════════════════════════════════════════════════════════════
def get_product_detail(item_id, shop_id, cookie_str=''):
    """STEP 7: Get product detail from Shopee public API.
    
    Endpoint: /api/v4/item/get?itemid=XXX&shopid=XXX
    Returns: dict with name, price, images[], or None
    """
    url = f"{SHOPEE_BASE}/api/v4/item/get"
    params = {'itemid': item_id, 'shopid': shop_id}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': f'{SHOPEE_BASE}/product/{shop_id}/{item_id}',
        'X-Shopee-Language': 'id',
    }
    if cookie_str:
        headers['Cookie'] = cookie_str

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None

        data = resp.json()
        item_data = data.get('data', data.get('item', {}))
        if not item_data:
            return None

        name = item_data.get('name', '')
        price = item_data.get('price', 0)
        if price > 100000:
            price = price // 100000
        price_max = item_data.get('price_max', 0)
        if price_max > 100000:
            price_max = price_max // 100000

        images = item_data.get('images', [])
        image = item_data.get('image', '')
        description = item_data.get('description', '')

        if not name:
            return None

        # Build image URL
        img_hash = images[0] if images else image
        if not img_hash:
            return None
        img_url = f"https://cf.shopee.co.id/file/{img_hash}"

        return {
            'name': name,
            'price': price or price_max,
            'image_url': img_url,
            'image_hash': img_hash,
            'images': images,
            'description': description[:200] if description else name,
        }

    except Exception as e:
        print(f"      [Detail] Error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════
def _generate_product_id(name, category):
    """Generate deterministic product ID from name + category."""
    raw = f"{category}_{name}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _download_image(url, filepath):
    """Download image and validate it."""
    try:
        resp = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/146.0.0.0'
        })
        if resp.status_code != 200 or len(resp.content) < 1000:
            return False

        content_type = resp.headers.get('content-type', '')
        if 'image' not in content_type and 'octet' not in content_type:
            return False

        with open(filepath, 'wb') as f:
            f.write(resp.content)
        return True
    except Exception:
        return False


def _to_affiliate_url(url):
    """Convert product URL to affiliate link."""
    aff_id = os.environ.get('AFFILIATE_ID_SHOPEE', '')
    if not aff_id or not url:
        return url
    if '/universal-link/' in url:
        return url
    if '/product/' in url:
        url = url.replace('/product/', '/universal-link/product/')
    if 'utm_source' not in url:
        sep = '&' if '?' in url else '?'
        url += f"{sep}utm_source=an_{aff_id}&utm_medium=affiliates"
    return url


def _matches_category(name, category):
    """Check if product name matches category keywords."""
    name_lower = name.lower()
    keywords = CATEGORY_KEYWORDS.get(category, [])
    return any(kw in name_lower for kw in keywords)


# ═══════════════════════════════════════════════════════════════════
#  STEP 8: MAIN COLLECTOR — COMBINE ALL STEPS
# ═══════════════════════════════════════════════════════════════════
def collect_products(categories=None, target=None):
    """Main collection: 2 API calls per product, that's it.
    
    API 1: affiliate product list → item_id + shop_id
    API 2: product detail → name, price, image
    """
    print("=" * 60)
    print("  PRODUCT COLLECTOR v2 — Simple 2-API Approach")
    print("=" * 60)

    if categories is None:
        categories = CATEGORIES
    if target is None:
        target = TARGET_PER_CATEGORY

    # STEP 1-2: Build request
    cookie_str, headers = _build_cookies_and_headers()
    if not headers:
        print("\n  ❌ Cannot proceed without cookies!")
        sys.exit(1)

    print(f"\n  ✅ Cookies loaded ({len(cookie_str)} chars)")

    # Health check
    print("\n  Testing affiliate API...")
    try:
        test_url = f"{AFFILIATE_BASE}/api/v3/offer/product/list"
        test_params = {'list_type': 5, 'sort_type': 5, 'page_offset': 0,
                       'page_limit': 1, 'client_type': 1}
        resp = requests.get(test_url, params=test_params, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 0:
                total = data.get('data', {}).get('total_count', 0)
                print(f"  ✅ Affiliate API works! ({total} products available)")
            else:
                err = data.get('error', '?')
                print(f"  ❌ API error: {err}")
                print(f"  Response: {resp.text[:300]}")
                sys.exit(1)
        else:
            print(f"  ❌ HTTP {resp.status_code}")
            print(f"  Response: {resp.text[:300]}")
            sys.exit(1)
    except Exception as e:
        print(f"  ❌ Connection error: {e}")
        sys.exit(1)

    # STEP 3-5: Get product list (all at once, filter per category later)
    print(f"\n  Fetching product list (target: {target} per category)...")
    total_needed = target * len(categories)
    all_offers = get_affiliate_products(headers, target=total_needed)
    print(f"\n  Got {len(all_offers)} product offers total")

    if not all_offers:
        print("  ❌ No products from affiliate API!")
        sys.exit(1)

    # STEP 6-8: For each product, get detail and save
    stats = {cat: {'new': 0, 'failed': 0, 'skipped': 0} for cat in categories}

    for category in categories:
        print(f"\n--- Category: {category.upper()} ---")
        collected = 0

        for offer in all_offers:
            if collected >= target:
                break

            # STEP 6: Extract IDs
            item_id, shop_id = extract_product_ids(offer)
            if not item_id or not shop_id:
                continue

            # Get name from offer for category matching
            nested = offer.get('batch_item_for_item_card_full', {})
            offer_name = ''
            if isinstance(nested, dict):
                offer_name = nested.get('name', '')
            if not offer_name:
                offer_name = offer.get('product_name', offer.get('item_name', ''))

            # Filter by category (skip if doesn't match)
            if offer_name and not _matches_category(offer_name, category):
                continue

            # Check if already in bank
            pid = _generate_product_id(offer_name or str(item_id), category)
            product_dir = os.path.join(BANK_DIR, category, pid)
            if os.path.exists(os.path.join(product_dir, 'image.jpg')):
                stats[category]['skipped'] += 1
                continue

            # STEP 7: Get product detail
            time.sleep(random.uniform(0.3, 1.0))
            detail = get_product_detail(item_id, shop_id, cookie_str)

            if not detail:
                stats[category]['failed'] += 1
                continue

            name = detail['name']
            price = detail['price']
            img_url = detail['image_url']

            # Double check category match with real product name
            if not _matches_category(name, category):
                continue

            # Download image
            os.makedirs(product_dir, exist_ok=True)
            img_path = os.path.join(product_dir, 'image.jpg')

            if not _download_image(img_url, img_path):
                stats[category]['failed'] += 1
                continue

            # Build affiliate URL
            product_link = offer.get('long_link', offer.get('product_link', ''))
            if not product_link:
                product_link = f"{SHOPEE_BASE}/product/{shop_id}/{item_id}"
            affiliate_url = _to_affiliate_url(product_link)

            # Get commission
            commission = (
                offer.get('seller_commission_rate') or
                offer.get('max_commission_rate') or
                offer.get('commission_rate') or '0%'
            )

            # Save product.json
            info = {
                'produk_id': pid,
                'nama': name[:80],
                'price': f"Rp{price:,}".replace(',', '.') if price > 0 else 'Lihat di Shopee',
                'desc': detail.get('description', name)[:200],
                'shopee_url': affiliate_url,
                'image_url': img_url,
                'category': category,
                'source': 'shopee_affiliate_v2',
                'commission': commission,
                'item_id': item_id,
                'shop_id': shop_id,
                'collected_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            }

            info_path = os.path.join(product_dir, 'product.json')
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, indent=2, ensure_ascii=False)

            collected += 1
            stats[category]['new'] += 1
            print(f"  ✓ {name[:50]} | Rp{price:,} | {commission}")

        print(f"  → {category}: {collected} new products")

    # ── SUMMARY ──
    print(f"\n{'=' * 60}")
    print("  COLLECTION SUMMARY")
    print("=" * 60)
    total_new = 0
    for cat in categories:
        s = stats[cat]
        total_new += s['new']
        print(f"  {cat:12s}: {s['new']:3d} new, {s['failed']:3d} failed, {s['skipped']:3d} skipped")
    print(f"  {'TOTAL':12s}: {total_new} new products")
    print("=" * 60)

    # ── EXPORT CSV ──
    _export_csv(categories)

    # ── COPY IMAGES ──
    _copy_images(categories)

    return total_new


def _export_csv(categories):
    """Export product bank to CSV for video engine."""
    import csv
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'produk.csv')
    products = []

    for cat in categories:
        cat_dir = os.path.join(BANK_DIR, cat)
        if not os.path.exists(cat_dir):
            continue
        for d in os.listdir(cat_dir):
            json_path = os.path.join(cat_dir, d, 'product.json')
            img_path = os.path.join(cat_dir, d, 'image.jpg')
            if os.path.exists(json_path) and os.path.exists(img_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        info = json.load(f)

                    # Validate: reject garbage
                    price = info.get('price', '')
                    if isinstance(price, str) and 'komisi' in price.lower():
                        continue
                    if info.get('source') == 'shopee_affiliate_shop':
                        continue

                    products.append(info)
                except Exception:
                    continue

    if not products:
        print("\n  ⚠️ No valid products for CSV!")
        return

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['nama', 'price', 'desc', 'shopee_url', 'image_url', 'category', 'source'])
        writer.writeheader()
        for p in products:
            writer.writerow({
                'nama': p.get('nama', ''),
                'price': p.get('price', ''),
                'desc': p.get('desc', ''),
                'shopee_url': p.get('shopee_url', ''),
                'image_url': p.get('image_url', ''),
                'category': p.get('category', ''),
                'source': p.get('source', ''),
            })

    print(f"\n  ✅ Exported {len(products)} products to CSV")


def _copy_images(categories):
    """Copy images to engine/data/images/ for video engine."""
    images_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'images')
    os.makedirs(images_dir, exist_ok=True)
    import shutil
    count = 0

    for cat in categories:
        cat_dir = os.path.join(BANK_DIR, cat)
        if not os.path.exists(cat_dir):
            continue
        for d in os.listdir(cat_dir):
            src = os.path.join(cat_dir, d, 'image.jpg')
            if os.path.exists(src):
                dst = os.path.join(images_dir, f"{d}.jpg")
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    count += 1

    print(f"  ✅ Copied {count} images")


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Shopee Product Collector v2')
    parser.add_argument('--category', default='', help='Single category (empty=all)')
    parser.add_argument('--target', type=int, default=25, help='Target per category')
    args = parser.parse_args()

    cats = [args.category] if args.category else None
    total = collect_products(categories=cats, target=args.target)

    if total == 0:
        print("\n  ❌ FAIL: No products collected!")
        sys.exit(1)
    else:
        print(f"\n  ✅ SUCCESS: {total} products collected!")
