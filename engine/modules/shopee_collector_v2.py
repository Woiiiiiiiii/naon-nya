"""
shopee_collector_v2.py
Product collector — EXACT 9 steps.

STEP 1-2: Cookies → headers (copy dari browser)
STEP 3:   Pagination (page_offset)
STEP 4:   Keyword filter per kategori
STEP 5:   Loop sampai 25 produk
STEP 6:   Extract item_id + shop_id
STEP 7:   Hit /api/v4/item/get → name, price, images
STEP 8:   Gabungin semua
STEP 9:   Cuma 2 request: affiliate + product detail. Titik.

Only needs: SHOPEE_AFFILIATE_COOKIES
"""

import os
import sys
import json
import time
import random
import hashlib
import requests
from urllib.parse import unquote

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
AFFILIATE_BASE = 'https://affiliate.shopee.co.id'
SHOPEE_BASE = 'https://shopee.co.id'
BANK_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'product_bank')
TARGET_PER_CATEGORY = 25

CATEGORIES = {
    'fashion': ['tas', 'sepatu', 'jam tangan'],
    'gadget': ['earphone', 'powerbank', 'smartwatch'],
    'beauty': ['skincare', 'serum', 'sunscreen'],
    'home': ['lampu', 'organizer', 'vacuum'],
    'wellness': ['vitamin', 'botol minum', 'olahraga'],
}


# ═══════════════════════════════════════════════════════════════════
#  STEP 1: COPY EXACT HEADERS DARI BROWSER
# ═══════════════════════════════════════════════════════════════════
def build_headers():
    """Build headers dari SHOPEE_AFFILIATE_COOKIES.
    Exact copy dari browser Network tab.
    """
    raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not raw:
        print("❌ SHOPEE_AFFILIATE_COOKIES not set!")
        return None, None

    try:
        cookies = json.loads(raw)
    except Exception as e:
        print(f"❌ Cookie parse error: {e}")
        return None, None

    # Cookie string
    if isinstance(cookies, list):
        cookie_str = '; '.join(
            f"{c['name']}={c['value']}" for c in cookies if c.get('name')
        )
    elif isinstance(cookies, dict):
        cookie_str = '; '.join(f"{k}={v}" for k, v in cookies.items())
    else:
        return None, None

    # Extract csrf + sz token
    csrftoken = ''
    sz_token = ''
    if isinstance(cookies, list):
        for c in cookies:
            if c.get('name') == 'csrftoken':
                csrftoken = c['value']
            if c.get('name') == 'shopee_webUnique_ccd':
                sz_token = unquote(c['value'])

    # Exact browser headers (copy dari Network tab)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
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
#  STEP 2-5: HIT AFFILIATE API + PAGINATION + KEYWORD
# ═══════════════════════════════════════════════════════════════════
def get_products_by_keyword(headers, keyword, target=25):
    """STEP 2-5: Hit affiliate API with keyword, paginate sampai target.
    
    Returns list of raw offer dicts.
    """
    url = f"{AFFILIATE_BASE}/api/v3/offer/product/list"
    products = []
    page = 0
    page_size = 20

    while len(products) < target:
        params = {
            'list_type': 5,
            'sort_type': 5,
            'page_offset': page * page_size,
            'page_limit': page_size,
            'client_type': 1,
            'keyword': keyword,
        }

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"      HTTP {resp.status_code}")
                break

            data = resp.json()
            if data.get('code') != 0:
                print(f"      API error: {data.get('error', data.get('code'))}")
                break

            items = data.get('data', {}).get('list', [])
            if not items:
                break

            products.extend(items)
            page += 1
            time.sleep(random.uniform(0.5, 1.0))

        except Exception as e:
            print(f"      Error: {e}")
            break

    return products[:target]


# ═══════════════════════════════════════════════════════════════════
#  STEP 6: EXTRACT item_id & shop_id
# ═══════════════════════════════════════════════════════════════════
def extract_ids(offer):
    """STEP 6: Ambil item_id + shop_id dari response."""
    item_id = offer.get('item_id', 0)
    shop_id = offer.get('shop_id', 0)

    # Coba dari nested
    nested = offer.get('batch_item_for_item_card_full', {})
    if isinstance(nested, dict):
        item_id = item_id or nested.get('itemid', 0)
        shop_id = shop_id or nested.get('shopid', 0)

    # Coba dari product_link
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

    return item_id, shop_id


# ═══════════════════════════════════════════════════════════════════
#  STEP 7: HIT /api/v4/item/get → name, price, images
# ═══════════════════════════════════════════════════════════════════
def get_product_detail(item_id, shop_id):
    """STEP 7: Hit product API, ambil name + price + images.
    
    Endpoint public — tanpa cookies juga bisa.
    """
    url = f"{SHOPEE_BASE}/api/v4/item/get"
    params = {'itemid': item_id, 'shopid': shop_id}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': f'{SHOPEE_BASE}/product/{shop_id}/{item_id}',
        'X-Shopee-Language': 'id',
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None

        data = resp.json()
        item = data.get('data', data.get('item', {}))
        if not item or not item.get('name'):
            return None

        # Price (Shopee uses price * 100000)
        price = item.get('price', 0)
        if price > 100000:
            price = price // 100000

        # Images
        images = item.get('images', [])
        image = item.get('image', '')
        img_hash = images[0] if images else image
        if not img_hash:
            return None

        return {
            'name': item['name'],
            'price': price,
            'image_hash': img_hash,
            'image_url': f"https://cf.shopee.co.id/file/{img_hash}",
        }

    except Exception as e:
        print(f"      Detail error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════
def _gen_id(name, cat):
    return hashlib.md5(f"{cat}_{name}".lower().encode()).hexdigest()[:12]


def _download_image(url, path):
    try:
        resp = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 Chrome/146.0.0.0',
            'Referer': 'https://shopee.co.id/',
        })
        if resp.status_code == 200 and len(resp.content) >= 1000:
            with open(path, 'wb') as f:
                f.write(resp.content)
            return True
    except Exception:
        pass
    return False


def _affiliate_url(url):
    aff = os.environ.get('AFFILIATE_ID_SHOPEE', '')
    if not aff or not url:
        return url
    if '/universal-link/' in url:
        return url
    url = url.replace('/product/', '/universal-link/product/')
    if 'utm_source' not in url:
        sep = '&' if '?' in url else '?'
        url += f"{sep}utm_source=an_{aff}&utm_medium=affiliates"
    return url


# ═══════════════════════════════════════════════════════════════════
#  STEP 8: GABUNGIN SEMUA
# ═══════════════════════════════════════════════════════════════════
def collect(categories=None, target=None):
    """STEP 8: Main loop.
    
    FOR tiap kategori:
        produk_list = ambil dari affiliate (keyword)
        LOOP sampai 25:
            ambil itemid + shopid
            hit product API
            ambil title, price, image
            simpan
    """
    print("=" * 60)
    print("  PRODUCT COLLECTOR v2")
    print("  2 request saja: affiliate + product detail")
    print("=" * 60)

    if categories is None:
        categories = CATEGORIES
    if target is None:
        target = TARGET_PER_CATEGORY

    # STEP 1: Build headers
    cookie_str, headers = build_headers()
    if not headers:
        sys.exit(1)
    print(f"\n✅ Cookies loaded ({len(cookie_str)} chars)")

    total_new = 0

    for cat, keywords in categories.items():
        print(f"\n{'─' * 40}")
        print(f"  KATEGORI: {cat.upper()}")
        print(f"{'─' * 40}")
        collected = 0

        for kw in keywords:
            if collected >= target:
                break

            # STEP 2-5: Hit affiliate API with keyword + pagination
            print(f"\n    Keyword: '{kw}'")
            offers = get_products_by_keyword(headers, kw, target=target - collected)
            print(f"    → {len(offers)} offers")

            for offer in offers:
                if collected >= target:
                    break

                # STEP 6: Extract item_id + shop_id
                item_id, shop_id = extract_ids(offer)
                if not item_id or not shop_id:
                    continue

                # Skip kalau sudah ada
                # Pakai nama sementara dari offer untuk generate ID
                nested = offer.get('batch_item_for_item_card_full', {})
                tmp_name = ''
                if isinstance(nested, dict):
                    tmp_name = nested.get('name', '')
                tmp_name = tmp_name or offer.get('product_name', str(item_id))

                pid = _gen_id(tmp_name, cat)
                product_dir = os.path.join(BANK_DIR, cat, pid)
                if os.path.exists(os.path.join(product_dir, 'image.jpg')):
                    continue

                # STEP 7: Hit product API → name, price, images
                time.sleep(random.uniform(0.3, 0.8))
                detail = get_product_detail(item_id, shop_id)

                if not detail:
                    continue

                # Re-generate ID with real name
                pid = _gen_id(detail['name'], cat)
                product_dir = os.path.join(BANK_DIR, cat, pid)
                if os.path.exists(os.path.join(product_dir, 'image.jpg')):
                    continue

                # Download image
                os.makedirs(product_dir, exist_ok=True)
                img_path = os.path.join(product_dir, 'image.jpg')

                if not _download_image(detail['image_url'], img_path):
                    try:
                        os.rmdir(product_dir)
                    except OSError:
                        pass
                    continue

                # Build affiliate URL
                link = offer.get('long_link', offer.get('product_link', ''))
                if not link:
                    link = f"{SHOPEE_BASE}/product/{shop_id}/{item_id}"

                # Commission
                commission = (
                    offer.get('seller_commission_rate') or
                    offer.get('max_commission_rate') or
                    offer.get('commission_rate') or '0%'
                )

                # Price format
                price = detail['price']
                price_str = f"Rp{price:,}".replace(',', '.') if price > 0 else 'Lihat di Shopee'

                # Save product.json
                info = {
                    'produk_id': pid,
                    'nama': detail['name'][:80],
                    'price': price_str,
                    'desc': detail['name'][:200],
                    'shopee_url': _affiliate_url(link),
                    'image_url': detail['image_url'],
                    'category': cat,
                    'source': 'shopee_affiliate_v2',
                    'commission': commission,
                    'item_id': item_id,
                    'shop_id': shop_id,
                    'collected_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                }

                with open(os.path.join(product_dir, 'product.json'), 'w', encoding='utf-8') as f:
                    json.dump(info, f, indent=2, ensure_ascii=False)

                collected += 1
                total_new += 1
                print(f"    ✓ {detail['name'][:45]} | {price_str} | {commission}")

        print(f"  → {cat}: {collected} produk baru")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  TOTAL: {total_new} produk baru")
    print("=" * 60)

    # Export CSV
    _export_csv()
    _copy_images()

    return total_new


def _export_csv():
    import csv
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'produk.csv')
    products = []
    for cat in CATEGORIES:
        cat_dir = os.path.join(BANK_DIR, cat)
        if not os.path.exists(cat_dir):
            continue
        for d in os.listdir(cat_dir):
            jp = os.path.join(cat_dir, d, 'product.json')
            ip = os.path.join(cat_dir, d, 'image.jpg')
            if os.path.exists(jp) and os.path.exists(ip):
                try:
                    with open(jp, 'r', encoding='utf-8') as f:
                        products.append(json.load(f))
                except Exception:
                    pass

    if not products:
        print("\n⚠️ No products for CSV")
        return

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    fields = ['nama', 'price', 'desc', 'shopee_url', 'image_url', 'category', 'source']
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for p in products:
            w.writerow({k: p.get(k, '') for k in fields})
    print(f"\n✅ CSV: {len(products)} products exported")


def _copy_images():
    import shutil
    dst_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'images')
    os.makedirs(dst_dir, exist_ok=True)
    count = 0
    for cat in CATEGORIES:
        cat_dir = os.path.join(BANK_DIR, cat)
        if not os.path.exists(cat_dir):
            continue
        for d in os.listdir(cat_dir):
            src = os.path.join(cat_dir, d, 'image.jpg')
            dst = os.path.join(dst_dir, f"{d}.jpg")
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                count += 1
    print(f"✅ Images: {count} copied")


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--category', default='')
    parser.add_argument('--target', type=int, default=25)
    args = parser.parse_args()

    cats = None
    if args.category:
        if args.category in CATEGORIES:
            cats = {args.category: CATEGORIES[args.category]}
        else:
            print(f"Category '{args.category}' not found")
            sys.exit(1)

    total = collect(categories=cats, target=args.target)
    if total == 0:
        print("\n❌ No products collected!")
        sys.exit(1)
    else:
        print(f"\n✅ {total} products collected!")
