"""
shopee_collector_v2.py
Simple product collector following user's 9-step approach.

CORE INSIGHT: Affiliate product list response ALREADY contains
product details (name, image, price) in 'batch_item_for_item_card_full'.
So we only need 1 API call + 1 image download. No second API needed.

Flow:
  1. affiliate.shopee.co.id/api/v3/offer/product/list → product data
  2. cf.shopee.co.id/file/{image_hash} → download image

Only needs: SHOPEE_AFFILIATE_COOKIES
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

# Broader keywords for category classification
CATEGORY_KEYWORDS = {
    'fashion': ['tas', 'sepatu', 'jam tangan', 'kaos', 'dompet', 'kacamata',
                'gelang', 'hoodie', 'jaket', 'dress', 'celana', 'baju', 'kemeja',
                'rok', 'sandal', 'topi', 'belt', 'ikat pinggang', 'sling bag',
                'backpack', 'ransel', 'sneakers', 'flatshoes', 'jersey', 'blazer',
                'cardigan', 'sweater', 'jeans', 'legging', 'kalung', 'cincin',
                'anting', 'bros', 'aksesoris', 'fashion', 'pakaian', 'bra',
                'underwear', 'swimwear', 'bikini', 'scarf', 'syal', 'sarung tangan'],
    'gadget': ['earphone', 'powerbank', 'charger', 'keyboard', 'mouse',
               'speaker', 'smartwatch', 'tripod', 'webcam', 'headphone',
               'headset', 'usb', 'kabel', 'adapter', 'case', 'casing',
               'screen protector', 'tempered glass', 'selfie', 'holder',
               'stand', 'hub', 'ssd', 'hardisk', 'flashdisk', 'memory',
               'microsd', 'led', 'ring light', 'gimbal', 'drone', 'gopro',
               'tablet', 'laptop', 'monitor', 'printer', 'router', 'modem',
               'gaming', 'controller', 'joystick', 'vr', 'bluetooth', 'wireless',
               'TWS', 'earbuds', 'gadget', 'elektronik', 'tech'],
    'beauty': ['serum', 'sunscreen', 'moisturizer', 'lip tint', 'cushion',
               'skincare', 'makeup', 'mascara', 'foundation', 'toner',
               'cleanser', 'facial wash', 'eye cream', 'night cream',
               'essence', 'ampoule', 'sheet mask', 'masker', 'lip balm',
               'lipstick', 'blush', 'bronzer', 'concealer', 'primer',
               'setting spray', 'eyeshadow', 'eyeliner', 'pensil alis',
               'beauty', 'kecantikan', 'parfum', 'body lotion', 'hair',
               'shampoo', 'conditioner', 'nail', 'kutek', 'lash', 'bulu mata',
               'brush', 'sponge', 'mirror', 'cotton', 'kapas'],
    'home': ['rak', 'lampu', 'organizer', 'vacuum', 'dapur',
             'bantal', 'dispenser', 'timbangan', 'gorden', 'sapu',
             'pel', 'tempat sampah', 'storage', 'box', 'container',
             'hanger', 'gantungan', 'keset', 'sprei', 'selimut',
             'handuk', 'tirai', 'jam dinding', 'cermin', 'lem',
             'stiker', 'wallpaper', 'pot', 'tanaman', 'taman',
             'piring', 'mangkok', 'gelas', 'sendok', 'garpu',
             'pisau', 'talenan', 'wajan', 'panci', 'rice cooker',
             'blender', 'mixer', 'oven', 'home', 'rumah', 'dekorasi',
             'furniture', 'meja', 'kursi', 'sofa', 'lemari'],
    'wellness': ['yoga', 'botol minum', 'gym', 'vitamin', 'massage',
                 'resistance band', 'matras', 'shaker', 'dumbell', 'termos',
                 'fitness', 'olahraga', 'kesehatan', 'health', 'supplement',
                 'protein', 'diet', 'weight', 'timbangan badan', 'tensimeter',
                 'termometer', 'oximeter', 'masker medis', 'plester',
                 'essential oil', 'diffuser', 'humidifier', 'air purifier',
                 'sport', 'running', 'sepeda', 'berenang', 'swimming',
                 'badminton', 'tenis', 'bola', 'skipping', 'push up',
                 'wellness', 'relax', 'aromatherapy', 'minyak kayu putih'],
}


# ═══════════════════════════════════════════════════════════════════
#  STEP 1-2: BUILD REQUEST FROM COOKIES
# ═══════════════════════════════════════════════════════════════════
def _build_cookies_and_headers():
    """Build cookie string + headers from SHOPEE_AFFILIATE_COOKIES."""
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

    # Extract useful cookies
    csrftoken = ''
    sz_token = ''
    if isinstance(cookies, list):
        for c in cookies:
            if c.get('name') == 'csrftoken':
                csrftoken = c.get('value', '')
            if c.get('name') == 'shopee_webUnique_ccd':
                sz_token = unquote(c.get('value', ''))

    # Headers matching exact Chrome browser
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
#  STEP 3-5: GET PRODUCT LIST + PAGINATION
# ═══════════════════════════════════════════════════════════════════
def _api_request(url, params, headers, cookie_str):
    """Make API request: try direct first, then CF Proxy fallback.
    Returns parsed JSON data or None.
    """
    from urllib.parse import urlencode
    full_url = f"{url}?{urlencode(params)}" if params else url

    # ── Try 1: Direct ──
    try:
        req_headers = headers.copy()
        resp = requests.get(full_url, headers=req_headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 0:
                print(f"    ✅ Direct: OK")
                return data
            else:
                err = data.get('error', data.get('code', '?'))
                print(f"    Direct: API error {err}")
        else:
            print(f"    Direct: HTTP {resp.status_code}")
    except Exception as e:
        print(f"    Direct: {e}")

    # ── Try 2: CF Proxy ──
    try:
        from shopee_proxy import proxy_get_json, is_proxy_available
        if is_proxy_available():
            # Pass headers WITHOUT Cookie (proxy handles it separately)
            proxy_headers = {k: v for k, v in headers.items() if k != 'Cookie'}
            status, data = proxy_get_json(full_url, headers=proxy_headers,
                                          cookies_str=cookie_str)
            if status == 200 and data and data.get('code') == 0:
                print(f"    ✅ Proxy: OK")
                return data
            else:
                err = data.get('error', '?') if data else '?'
                print(f"    Proxy: HTTP {status}, error={err}")
        else:
            print(f"    Proxy: not configured")
    except ImportError:
        print(f"    Proxy: shopee_proxy.py not found")
    except Exception as e:
        print(f"    Proxy: {e}")

    return None


def get_affiliate_products(headers, cookie_str, target=100):
    """Fetch product list from affiliate API with pagination.
    Uses direct request first, CF Proxy as fallback.
    """
    url = f"{AFFILIATE_BASE}/api/v3/offer/product/list"
    products = []
    page = 0
    page_size = 20
    max_pages = 15

    while len(products) < target and page < max_pages:
        params = {
            'list_type': 5,
            'sort_type': 5,
            'page_offset': page * page_size,
            'page_limit': page_size,
            'client_type': 1,
        }

        print(f"    [Page {page+1}]")
        data = _api_request(url, params, headers, cookie_str)

        if not data:
            print(f"    ❌ Failed to get page {page+1}")
            break

        items = data.get('data', {}).get('list', [])
        total = data.get('data', {}).get('total_count', 0)

        if not items:
            break

        if page == 0:
            print(f"    Total available: {total}")
            print(f"    Item keys: {list(items[0].keys())}")
            nested = items[0].get('batch_item_for_item_card_full', {})
            if isinstance(nested, dict) and nested:
                print(f"    Nested keys: {list(nested.keys())}")

        products.extend(items)
        print(f"    +{len(items)} items (collected: {len(products)})")
        page += 1
        time.sleep(random.uniform(0.5, 1.5))

    return products


# ═══════════════════════════════════════════════════════════════════
#  STEP 6: EXTRACT PRODUCT DATA FROM RESPONSE 
#  (name, price, image, item_id, shop_id — ALL from one response)
# ═══════════════════════════════════════════════════════════════════
def parse_product(offer):
    """Extract all product data directly from affiliate response.
    No second API call needed — data is embedded in response.
    
    Returns dict or None.
    """
    # STEP 6: Get item_id and shop_id
    item_id = offer.get('item_id', 0)
    shop_id = offer.get('shop_id', 0)

    # Get nested product card (contains name, image, price)
    nested = offer.get('batch_item_for_item_card_full', {})
    if not isinstance(nested, dict):
        nested = {}

    # Name: try nested first, then top-level
    name = (
        nested.get('name') or nested.get('item_name') or
        offer.get('product_name') or offer.get('item_name') or
        offer.get('name') or ''
    )
    if not name or len(name.strip()) < 3:
        return None

    # Image: nested or top-level
    image = (
        nested.get('image') or nested.get('item_image') or
        offer.get('product_image') or offer.get('image') or ''
    )

    # Item ID / Shop ID from nested if missing
    if not item_id:
        item_id = nested.get('itemid') or nested.get('item_id') or 0
    if not shop_id:
        shop_id = nested.get('shopid') or nested.get('shop_id') or 0

    # Try parse from product link
    if not item_id or not shop_id:
        link = offer.get('product_link', offer.get('long_link', ''))
        if '/product/' in link:
            parts = link.split('/product/')[-1].split('?')[0].split('/')
            if len(parts) >= 2:
                try:
                    shop_id = shop_id or int(parts[0])
                    item_id = item_id or int(parts[1])
                except ValueError:
                    pass

    # Price (Shopee prices are in units * 100000)
    price = (
        nested.get('price') or nested.get('price_min') or
        offer.get('price') or offer.get('product_price') or 0
    )
    if isinstance(price, (int, float)) and price > 100000:
        price = int(price // 100000)

    # Build image URL
    if image and not image.startswith('http'):
        image_url = f"https://cf.shopee.co.id/file/{image}"
    elif image:
        image_url = image
    else:
        return None

    # Affiliate link
    product_link = offer.get('long_link') or offer.get('product_link') or ''
    if not product_link and shop_id and item_id:
        product_link = f"{SHOPEE_BASE}/product/{shop_id}/{item_id}"

    # Commission
    commission = (
        offer.get('seller_commission_rate') or
        offer.get('max_commission_rate') or
        offer.get('commission_rate') or '0%'
    )

    return {
        'nama': name.strip()[:80],
        'price': f"Rp{price:,}".replace(',', '.') if isinstance(price, (int, float)) and price > 0 else 'Lihat di Shopee',
        'desc': name.strip()[:200],
        'image_url': image_url,
        'shopee_url': product_link,
        'source': 'shopee_affiliate_v2',
        'commission': commission,
        'item_id': item_id,
        'shop_id': shop_id,
    }


# ═══════════════════════════════════════════════════════════════════
#  CATEGORY MATCHING
# ═══════════════════════════════════════════════════════════════════
def classify_category(name):
    """Classify product to best matching category. Returns category or None."""
    name_lower = name.lower()
    best_cat = None
    best_score = 0

    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in name_lower)
        if score > best_score:
            best_score = score
            best_cat = cat

    return best_cat if best_score > 0 else None


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════
def _generate_product_id(name, category):
    raw = f"{category}_{name}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _download_image(url, filepath):
    """Download image: try direct, then CF Proxy fallback."""
    # Try 1: Direct
    try:
        resp = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/146.0.0.0',
            'Referer': 'https://shopee.co.id/',
        })
        if resp.status_code == 200 and len(resp.content) >= 1000:
            content_type = resp.headers.get('content-type', '')
            if 'image' in content_type or 'octet' in content_type:
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                return True
    except Exception:
        pass

    # Try 2: CF Proxy
    try:
        from shopee_proxy import proxy_download_image, is_proxy_available
        if is_proxy_available():
            return proxy_download_image(url, filepath, min_size=1000)
    except ImportError:
        pass
    except Exception:
        pass

    return False


def _to_affiliate_url(url):
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


# ═══════════════════════════════════════════════════════════════════
#  STEP 8: MAIN — COMBINE ALL
# ═══════════════════════════════════════════════════════════════════
PREFETCH_FILE = '/tmp/affiliate_products.json'


def _load_prefetched():
    """Load pre-fetched products from browser step.
    Returns: dict {category: [offers]} or None
    """
    if not os.path.exists(PREFETCH_FILE):
        return None
    try:
        with open(PREFETCH_FILE, 'r') as f:
            data = json.load(f)
        if isinstance(data, dict) and any(data.values()):
            total = sum(len(v) for v in data.values())
            print(f"  ✅ Pre-fetched data found: {total} products from browser")
            return data
    except Exception as e:
        print(f"  ⚠️ Pre-fetch read error: {e}")
    return None


def collect_products(categories=None, target=None):
    """Main collection with 3 data sources (in priority order):
    
    1. Pre-fetch file (from Playwright browser — bypasses anti-bot)
    2. Direct API call (works from local PC)
    3. CF Proxy fallback (for GitHub Actions)
    """
    print("=" * 60)
    print("  PRODUCT COLLECTOR v2 — Simple Approach")
    print("=" * 60)

    if categories is None:
        categories = CATEGORIES
    if target is None:
        target = TARGET_PER_CATEGORY

    # STEP 1-2: Cookies → headers
    cookie_str, headers = _build_cookies_and_headers()
    if not headers:
        print("\n  ❌ Cannot proceed without cookies!")
        sys.exit(1)
    print(f"\n  ✅ Cookies loaded ({len(cookie_str)} chars)")

    # Check proxy availability
    try:
        from shopee_proxy import is_proxy_available
        if is_proxy_available():
            print("  ✅ CF Proxy available (fallback enabled)")
        else:
            print("  ⚠️ CF Proxy not configured (direct only)")
    except ImportError:
        print("  ⚠️ shopee_proxy.py not found")

    # ── SOURCE 1: Pre-fetched data from browser ──
    all_offers = []
    prefetched = _load_prefetched()

    if prefetched:
        # Pre-fetch data is organized by category
        for cat in categories:
            cat_offers = prefetched.get(cat, [])
            all_offers.extend(cat_offers)
        # Also include offers from non-requested categories
        for cat, offers in prefetched.items():
            if cat not in categories:
                all_offers.extend(offers)
        print(f"  Using {len(all_offers)} pre-fetched products")

    # ── SOURCE 2+3: Direct API + CF Proxy fallback ──
    if not all_offers:
        print("\n  No pre-fetch data, trying HTTP API...")
        total_needed = target * len(categories) * 3
        all_offers = get_affiliate_products(headers, cookie_str,
                                            target=min(total_needed, 200))

    if not all_offers:
        print("  ❌ No products from affiliate API!")
        print("  Check: SHOPEE_AFFILIATE_COOKIES, CF_PROXY_URL, CF_PROXY_KEY")
        sys.exit(1)

    print(f"\n  ✅ Got {len(all_offers)} product offers")

    # STEP 6-8: Parse, classify, save
    stats = {cat: {'new': 0, 'failed': 0, 'skipped': 0} for cat in categories}
    category_counts = {cat: 0 for cat in categories}
    unmatched = []

    for offer in all_offers:
        product = parse_product(offer)
        if not product:
            continue

        # Classify to category
        cat = classify_category(product['nama'])
        if cat and cat in categories and category_counts[cat] < target:
            _save_single(product, cat, category_counts, stats)
        else:
            unmatched.append(product)

    # Second pass: distribute unmatched products to categories that need more
    for product in unmatched:
        # Find category with fewest products
        need_cat = min(categories, key=lambda c: category_counts[c])
        if category_counts[need_cat] < target:
            _save_single(product, need_cat, category_counts, stats)

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

    # Export
    _export_csv(categories)
    _copy_images(categories)

    return total_new


def _save_single(product, category, counts, stats):
    """Save one product to bank."""
    pid = _generate_product_id(product['nama'], category)
    product_dir = os.path.join(BANK_DIR, category, pid)

    # Skip if exists
    if os.path.exists(os.path.join(product_dir, 'image.jpg')):
        stats[category]['skipped'] += 1
        return

    # Download image
    os.makedirs(product_dir, exist_ok=True)
    img_path = os.path.join(product_dir, 'image.jpg')

    if not _download_image(product['image_url'], img_path):
        stats[category]['failed'] += 1
        # Clean up empty dir
        try:
            os.rmdir(product_dir)
        except OSError:
            pass
        return

    # Convert to affiliate URL
    product['shopee_url'] = _to_affiliate_url(product['shopee_url'])
    product['category'] = category
    product['produk_id'] = pid
    product['collected_at'] = time.strftime('%Y-%m-%d %H:%M:%S')

    info_path = os.path.join(product_dir, 'product.json')
    with open(info_path, 'w', encoding='utf-8') as f:
        json.dump(product, f, indent=2, ensure_ascii=False)

    counts[category] += 1
    stats[category]['new'] += 1
    print(f"  ✓ [{category}] {product['nama'][:45]} | {product['price']} | {product['commission']}")


def _export_csv(categories):
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
            writer.writerow({k: p.get(k, '') for k in writer.fieldnames})

    print(f"\n  ✅ Exported {len(products)} products to CSV")


def _copy_images(categories):
    import shutil
    images_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'images')
    os.makedirs(images_dir, exist_ok=True)
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
