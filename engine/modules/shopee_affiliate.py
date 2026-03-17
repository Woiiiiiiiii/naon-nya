"""
shopee_affiliate.py
Collect products via Shopee Affiliate Dashboard API.

Uses cookies from affiliate.shopee.co.id (NOT shopee.co.id belanja).
This endpoint is NOT blocked by error 90309999 because it's the affiliate
dashboard's own API, not the public search API.

Flow:
  1. GET /api/v3/offer/shop/list → get shops with affiliate links
  2. For each shop → get products via Shopee shop recommend API
  3. Build affiliate link per product using shop's UTM pattern
  4. Download clean product images from Shopee CDN

Environment:
  SHOPEE_AFFILIATE_COOKIES  = cookies from affiliate.shopee.co.id
  (fallback: SHOPEE_COOKIES if affiliate cookies not set)
"""

import os
import sys
import json
import time
import random
import hashlib
import requests
from urllib.parse import quote_plus, urlencode

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
AFFILIATE_BASE = "https://affiliate.shopee.co.id"
SHOPEE_BASE = "https://shopee.co.id"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
]

# Search keywords per category (same as product_collector.py)
AFFILIATE_KEYWORDS = {
    'fashion': ['tas wanita', 'sepatu sneakers', 'jam tangan', 'dompet kulit',
                'hoodie', 'kacamata', 'backpack', 'topi'],
    'gadget': ['earphone TWS', 'powerbank', 'mouse wireless', 'speaker bluetooth',
               'keyboard', 'charger', 'webcam', 'tripod'],
    'beauty': ['serum wajah', 'sunscreen', 'lip tint', 'moisturizer',
               'toner', 'cushion', 'masker wajah', 'skincare'],
    'home': ['rak organizer', 'lampu LED', 'vacuum cleaner', 'dispenser',
             'gorden', 'bantal', 'aroma diffuser', 'rak bumbu'],
    'wellness': ['botol minum', 'matras yoga', 'resistance band', 'shaker',
                 'timbangan digital', 'foam roller', 'alat pijat', 'termos'],
}


# ═══════════════════════════════════════════════════════════════════
#  SESSION BUILDER
# ═══════════════════════════════════════════════════════════════════
def _build_affiliate_session():
    """Build requests session with affiliate.shopee.co.id cookies."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json',
        'Accept-Language': 'id-ID,id;q=0.9,en;q=0.8',
        'Referer': f'{AFFILIATE_BASE}/offer/shopee',
        'Origin': AFFILIATE_BASE,
    })

    # Try affiliate cookies first, fallback to regular cookies
    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not cookies_raw:
        cookies_raw = os.environ.get('SHOPEE_COOKIES', '')
    if not cookies_raw:
        print("  [WARN] No affiliate cookies — set SHOPEE_AFFILIATE_COOKIES")
        return None

    try:
        cookies = json.loads(cookies_raw)
        if isinstance(cookies, list):
            for c in cookies:
                name = c.get('name', '')
                value = c.get('value', '')
                domain = c.get('domain', '.shopee.co.id')
                if name and value:
                    session.cookies.set(name, value, domain=domain)
        elif isinstance(cookies, dict):
            for name, value in cookies.items():
                session.cookies.set(name, str(value), domain='.shopee.co.id')
        print(f"  [OK] Affiliate session with {len(session.cookies)} cookies")
        return session
    except Exception as e:
        print(f"  [WARN] Failed to parse affiliate cookies: {e}")
        return None


def _build_cookie_string():
    """Build cookie string from env for proxy requests."""
    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not cookies_raw:
        cookies_raw = os.environ.get('SHOPEE_COOKIES', '')
    if not cookies_raw:
        return ''
    try:
        cookies = json.loads(cookies_raw)
        if isinstance(cookies, list):
            return '; '.join([f"{c.get('name','')}={c.get('value','')}"
                              for c in cookies if c.get('name')])
        elif isinstance(cookies, dict):
            return '; '.join([f'{k}={v}' for k, v in cookies.items()])
    except Exception:
        pass
    return ''


# ═══════════════════════════════════════════════════════════════════
#  STEP 1: GET SHOPS FROM AFFILIATE DASHBOARD API
# ═══════════════════════════════════════════════════════════════════
def get_affiliate_shops(keyword, session=None, limit=20):
    """Fetch shop offers from Shopee Affiliate Dashboard API.

    Endpoint: /api/v3/offer/shop/list
    Returns: list of shops with affiliate links + commission rates.

    This endpoint is NOT affected by error 90309999 (search block)
    because it's the affiliate dashboard's internal API."""
    url = f"{AFFILIATE_BASE}/api/v3/offer/shop/list"
    params = {
        'sort_type': 1,
        'page_offset': 0,
        'page_limit': limit,
        'keyword': keyword,
    }

    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json',
        'Referer': f'{AFFILIATE_BASE}/offer/shopee',
        'Origin': AFFILIATE_BASE,
        'X-Requested-With': 'XMLHttpRequest',
    }

    try:
        # Try via proxy first (in case direct is blocked from GitHub Actions IP)
        data = None
        try:
            from shopee_proxy import proxy_get_json, is_proxy_available
            if is_proxy_available():
                full_url = f"{url}?{urlencode(params)}"
                cookies_str = _build_cookie_string()
                status, data = proxy_get_json(full_url, headers=headers,
                                              cookies_str=cookies_str)
                if status != 200:
                    print(f"    [Affiliate] Proxy returned HTTP {status}")
                    data = None
        except ImportError:
            pass

        # Direct request (works if running locally or cookies valid)
        if data is None and session:
            resp = session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
            else:
                print(f"    [Affiliate] HTTP {resp.status_code} for '{keyword}'")
                return []

        if not data or data.get('code') != 0:
            print(f"    [Affiliate] API error: {data.get('msg', 'unknown') if data else 'no data'}")
            return []

        shops = data.get('data', {}).get('list', [])
        total = data.get('data', {}).get('total_count', 0)
        print(f"    [Affiliate] '{keyword}' → {len(shops)} shops (total {total})")
        return shops

    except Exception as e:
        print(f"    [Affiliate] Error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
#  STEP 2: GET PRODUCTS FROM SHOP
# ═══════════════════════════════════════════════════════════════════
def get_shop_products(shop_id, limit=6):
    """Get products from a specific Shopee shop using recommend API.
    Uses shop page recommendation — different from blocked search endpoint."""
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json',
        'Referer': f'{SHOPEE_BASE}/shop/{shop_id}',
        'X-Shopee-Language': 'id',
    }

    # Try shop recommend API (different endpoint from search)
    url = f"{SHOPEE_BASE}/api/v4/recommend/recommend"
    params = {
        'bundle': 'shop_page_product_tab_main',
        'limit': limit,
        'offset': 0,
        'shopid': shop_id,
    }

    try:
        data = None
        try:
            from shopee_proxy import proxy_get_json, is_proxy_available
            if is_proxy_available():
                full_url = f"{url}?{urlencode(params)}"
                status, data = proxy_get_json(full_url, headers=headers)
                if status != 200:
                    data = None
        except ImportError:
            pass

        if data is None:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()

        if not data:
            return []

        # Parse recommend response
        products = []
        sections = data.get('data', {}).get('sections', [])
        for section in sections:
            items = section.get('data', {}).get('item', [])
            for item in items[:limit]:
                if not isinstance(item, dict):
                    continue
                info = item.get('item_basic', item)
                name = info.get('name', '')
                item_id = info.get('itemid', 0)
                price = info.get('price', 0)
                if price > 100000:
                    price = price // 100000
                image_hash = info.get('image', '')

                if name and image_hash and item_id:
                    products.append({
                        'name': name,
                        'item_id': item_id,
                        'shop_id': shop_id,
                        'price': price,
                        'image_hash': image_hash,
                    })

        # Fallback: try shop search API (different from global search)
        if not products:
            url2 = f"{SHOPEE_BASE}/api/v4/shop/rcmd_items"
            params2 = {'shopid': shop_id, 'limit': limit}
            try:
                resp2 = requests.get(url2, params=params2, headers=headers, timeout=15)
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    for item in data2.get('items', [])[:limit]:
                        info = item.get('item_basic', item)
                        name = info.get('name', '')
                        item_id = info.get('itemid', 0)
                        price = info.get('price', 0)
                        if price > 100000:
                            price = price // 100000
                        image_hash = info.get('image', '')
                        if name and image_hash and item_id:
                            products.append({
                                'name': name,
                                'item_id': item_id,
                                'shop_id': shop_id,
                                'price': price,
                                'image_hash': image_hash,
                            })
            except Exception:
                pass

        return products

    except Exception as e:
        print(f"    [ShopProducts] Error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
#  STEP 3: BUILD AFFILIATE LINK
# ═══════════════════════════════════════════════════════════════════
def _extract_utm_params(long_link):
    """Extract UTM affiliate tracking parameters from shop's long_link.
    
    Input: https://shopee.co.id/universal-link/shop/XXX?utm_source=an_11344941723&...
    Returns: dict with utm params to apply to product links.
    """
    from urllib.parse import urlparse, parse_qs
    try:
        parsed = urlparse(long_link)
        params = parse_qs(parsed.query)
        # Flatten single-value params
        return {k: v[0] if len(v) == 1 else v for k, v in params.items()}
    except Exception:
        return {}


def build_product_affiliate_link(shop_id, item_id, long_link):
    """Build a product-level affiliate link using the shop's UTM tracking.
    
    Takes the UTM params from the shop's affiliate link and applies them
    to a product-level URL.
    """
    utm = _extract_utm_params(long_link)
    if not utm:
        # Fallback: just return regular product link
        return f"{SHOPEE_BASE}/product/{shop_id}/{item_id}"

    base = f"{SHOPEE_BASE}/universal-link/product/{shop_id}/{item_id}"
    query = urlencode(utm)
    return f"{base}?{query}"


# ═══════════════════════════════════════════════════════════════════
#  MAIN: COLLECT PRODUCTS VIA AFFILIATE API
# ═══════════════════════════════════════════════════════════════════
def collect_affiliate_products(category, target=5):
    """Collect products via Shopee Affiliate Dashboard API.
    
    Flow:
      1. Search shops in affiliate dashboard by keyword
      2. For top shops → get their products
      3. Build affiliate links for each product
      4. Return product list ready for bank storage
      
    Returns: list of dicts with nama, price, image_url, shopee_url, source, commission
    """
    print(f"\n  === Affiliate API: {category} (target={target}) ===")
    session = _build_affiliate_session()

    keywords = AFFILIATE_KEYWORDS.get(category, [category])
    # Rotate keywords: pick 2 per run
    random.shuffle(keywords)
    selected_keywords = keywords[:2]

    all_products = []

    for keyword in selected_keywords:
        if len(all_products) >= target:
            break

        print(f"\n  Searching affiliate shops: '{keyword}'...")
        time.sleep(random.uniform(1.0, 2.0))

        shops = get_affiliate_shops(keyword, session=session, limit=10)
        if not shops:
            continue

        # Pick top 3 shops (highest commission first)
        def _commission_sort(s):
            rate = s.get('commission_rate', '0%').replace('%', '').replace(',', '.')
            try:
                return float(rate)
            except ValueError:
                return 0
        shops_sorted = sorted(shops, key=_commission_sort, reverse=True)[:3]

        for shop in shops_sorted:
            if len(all_products) >= target:
                break

            shop_id = shop.get('shop_id', '')
            shop_name = shop.get('shop_name', '')
            shop_image = shop.get('shop_image', '')
            long_link = shop.get('long_link', '')
            commission = shop.get('commission_rate', '0%')

            print(f"    Shop: {shop_name} (commission={commission})")
            time.sleep(random.uniform(1.5, 3.0))

            # Get products from this shop
            shop_products = get_shop_products(shop_id, limit=4)

            if shop_products:
                # We got product-level data → use it
                for prod in shop_products:
                    if len(all_products) >= target:
                        break
                    image_hash = prod['image_hash']
                    img_url = f"https://down-id.img.susercontent.com/file/{image_hash}"
                    aff_link = build_product_affiliate_link(
                        shop_id, prod['item_id'], long_link)
                    price = prod['price']

                    all_products.append({
                        'nama': prod['name'][:80],
                        'price': f"Rp{price:,}".replace(',', '.') if price else 'Lihat harga',
                        'desc': prod['name'],
                        'image_url': img_url,
                        'shopee_url': aff_link,
                        'source': 'shopee_affiliate',
                        'commission': commission,
                        'shop_name': shop_name,
                    })
                    print(f"      ✓ Product: {prod['name'][:40]}")
            else:
                # Fallback: use shop as "product" (shop image + shop link)
                # This works for video content (shows the shop brand)
                all_products.append({
                    'nama': shop_name[:80],
                    'price': f"Komisi {commission}",
                    'desc': f"Toko {shop_name} - Komisi affiliate {commission}",
                    'image_url': shop_image,
                    'shopee_url': long_link,
                    'source': 'shopee_affiliate_shop',
                    'commission': commission,
                    'shop_name': shop_name,
                })
                print(f"      ✓ Shop fallback: {shop_name}")

    print(f"\n  → Affiliate API: {len(all_products)} products for {category}")
    return all_products


# ═══════════════════════════════════════════════════════════════════
#  STANDALONE TEST
# ═══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Shopee Affiliate Product Collector')
    parser.add_argument('--category', default='fashion', help='Category to collect')
    parser.add_argument('--target', type=int, default=5, help='Target products')
    args = parser.parse_args()

    products = collect_affiliate_products(args.category, args.target)
    print(f"\n{'='*60}")
    print(f"  RESULTS: {len(products)} products")
    print(f"{'='*60}")
    for i, p in enumerate(products, 1):
        print(f"  {i}. {p['nama'][:50]}")
        print(f"     Price: {p['price']}")
        print(f"     Source: {p['source']}")
        print(f"     Commission: {p.get('commission', 'N/A')}")
        print(f"     Link: {p['shopee_url'][:80]}...")
        print(f"     Image: {p['image_url'][:80]}...")
        print()
