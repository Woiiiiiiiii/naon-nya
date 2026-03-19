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
  Requires: SHOPEE_AFFILIATE_COOKIES environment variable
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

# Affiliate API searches by SHOP NAME, so use broad terms that match
# Shopee shop names (e.g., "Toko Tas Wanita", "Skincare Official").
# Single broad words work better than specific product descriptions.
AFFILIATE_KEYWORDS = {
    'fashion': ['tas', 'sepatu', 'jam tangan', 'dompet', 'hoodie',
                'kacamata', 'backpack', 'topi', 'fashion', 'baju',
                'celana', 'kaos', 'sneakers', 'sling bag'],
    'gadget': ['earphone', 'powerbank', 'mouse', 'speaker', 'keyboard',
               'charger', 'webcam', 'tripod', 'gadget', 'elektronik',
               'headphone', 'smartwatch', 'kabel', 'aksesoris HP'],
    'beauty': ['skincare', 'serum', 'sunscreen', 'makeup', 'kosmetik',
               'lip', 'moisturizer', 'cushion', 'masker wajah', 'beauty',
               'kecantikan', 'perawatan wajah', 'foundation', 'toner'],
    'home': ['rumah tangga', 'dapur', 'rak', 'lampu', 'organizer',
             'dekorasi', 'perabot', 'bantal', 'gorden', 'home',
             'vacuum', 'dispenser', 'tempat', 'alat dapur'],
    'wellness': ['kesehatan', 'olahraga', 'gym', 'fitness', 'yoga',
                 'sport', 'botol minum', 'termos', 'pijat', 'vitamin',
                 'suplemen', 'alat olahraga', 'outdoor', 'tumbler'],
}


# ═══════════════════════════════════════════════════════════════════
#  COOKIE VALIDATION
# ═══════════════════════════════════════════════════════════════════
_COOKIES_VALID = None  # Cached result: True/False/None (unknown)


def _check_cookie_expiry(cookies_raw):
    """Check if cookies are valid and not all expired.
    Does NOT require specific cookie names — the API health check
    (Step 4 in check_cookies_health) handles actual auth validation."""
    try:
        cookies = json.loads(cookies_raw)
        if not isinstance(cookies, list):
            return True  # Can't check dict format, assume OK

        import time as _time
        now = _time.time()
        total = len(cookies)
        expired = 0

        for c in cookies:
            exp = c.get('expirationDate', 0)
            is_session = c.get('session', False)
            if exp and exp < now and not is_session:
                expired += 1

        if expired > 0 and expired == total:
            print(f"  ⚠️  ALL {total} cookies expired! Please refresh.")
            return False

        if expired > 0:
            print(f"  [Cookies] {expired}/{total} cookies expired (some still valid)")

        return True
    except Exception:
        return True  # Can't check, assume OK


def check_cookies_health():
    """Quick API call to verify cookies are accepted by Shopee.
    Returns True if cookies work, False if expired/invalid.
    Caches result so it's only called once per run."""
    global _COOKIES_VALID
    if _COOKIES_VALID is not None:
        return _COOKIES_VALID

    # ── Step 1: Which env var are we using? ──
    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not cookies_raw:
        print("  ⚠️  SHOPEE_AFFILIATE_COOKIES not set!")
        print("  ⚠️  Set it in GitHub Secrets or use auto-login (SHOPEE_USERNAME/PASSWORD)")
        _COOKIES_VALID = False
        return False
    source = 'SHOPEE_AFFILIATE_COOKIES'

    print(f"  [Cookie Source] Using: {source} ({len(cookies_raw)} chars)")

    # ── Step 2: Parse and validate cookies ──
    try:
        cookies = json.loads(cookies_raw)
        if isinstance(cookies, list):
            import time as _time
            now = _time.time()
            
            domains_seen = set()
            total = len(cookies)
            expired_count = 0
            spc_cookies = []
            
            for c in cookies:
                name = c.get('name', '')
                domain = c.get('domain', '?')
                exp = c.get('expirationDate', 0)
                is_session = c.get('session', False)
                domains_seen.add(domain)
                
                if exp and exp < now and not is_session:
                    expired_count += 1
                
                if name.startswith('SPC_'):
                    spc_cookies.append(name)
            
            print(f"  [Cookies] Total: {total}, Expired: {expired_count}")
            print(f"  [Cookies] Domains: {', '.join(sorted(domains_seen))}")
            if spc_cookies:
                print(f"  [Cookies] SPC cookies: {', '.join(spc_cookies)}")
            
            # Warn if ALL cookies are expired
            if expired_count == total and total > 0:
                print(f"  ⚠️  ALL {total} cookies are expired!")
                _COOKIES_VALID = False
                return False
        else:
            print(f"  [Cookies] Dict format with {len(cookies)} entries")
    except Exception as e:
        print(f"  [Cookies] Parse error: {e}")
        _COOKIES_VALID = False
        return False

    # ── Step 3: Check expiry dates ──
    if not _check_cookie_expiry(cookies_raw):
        _COOKIES_VALID = False
        return False

    # ── Step 4: Quick API health check ──
    print("  [Health] Testing API with these cookies...")
    url = f"{AFFILIATE_BASE}/api/v3/offer/shop/list"
    params = {'sort_type': 1, 'page_offset': 0, 'page_limit': 1, 'keyword': 'tas'}
    
    data = _make_affiliate_request(url, params, label='HealthCheck')
    if data and data.get('code') == 0:
        print("  ✅ Affiliate cookies are VALID")
        _COOKIES_VALID = True
        return True
    else:
        code = data.get('code', '?') if data else '?'
        msg = data.get('msg', '?') if data else 'no response'
        print(f"  ❌ Affiliate cookies REJECTED: code={code}, msg={msg}")
        _COOKIES_VALID = False
        return False


# ═══════════════════════════════════════════════════════════════════
#  SESSION BUILDER
# ═══════════════════════════════════════════════════════════════════
def _build_affiliate_session():
    """Build requests session with affiliate.shopee.co.id cookies."""
    # Quick check: if cookies already known to be invalid, skip
    if _COOKIES_VALID is False:
        return None

    session = requests.Session()
    session.headers.update({
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json',
        'Accept-Language': 'id-ID,id;q=0.9,en;q=0.8',
        'Referer': f'{AFFILIATE_BASE}/offer/brand_offer',
        'Origin': AFFILIATE_BASE,
    })

    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not cookies_raw:
        print("  [WARN] SHOPEE_AFFILIATE_COOKIES not set")
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
    """Build cookie string from env for HTTP requests."""
    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
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


def _make_affiliate_request(url, params=None, session=None, label='API'):
    """Centralized request helper for affiliate.shopee.co.id.
    
    Strategy: Try DIRECT first (auto-login proves GitHub Actions 
    can reach affiliate.shopee.co.id), proxy as fallback.
    
    Returns: parsed JSON data or None
    """
    from urllib.parse import urlencode
    
    cookies_str = _build_cookie_string()
    full_url = f"{url}?{urlencode(params)}" if params else url
    
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json',
        'Accept-Language': 'id-ID,id;q=0.9,en;q=0.8',
        'Referer': f'{AFFILIATE_BASE}/offer/brand_offer',
        'Origin': AFFILIATE_BASE,
        'X-Requested-With': 'XMLHttpRequest',
        'sec-ch-ua': '"Not A(Brand";v="99", "Chromium";v="121"',
        'sec-ch-ua-platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }
    
    # Extract csrftoken from cookies if available
    try:
        cookies = json.loads(os.environ.get('SHOPEE_AFFILIATE_COOKIES', '[]'))
        if isinstance(cookies, list):
            for c in cookies:
                if c.get('name') == 'csrftoken':
                    headers['x-csrftoken'] = c.get('value', '')
                    break
    except Exception:
        pass
    
    data = None
    
    # ── Method 1: Direct with session (if available) ──
    if session and data is None:
        try:
            resp = session.get(url, params=params, headers=headers, timeout=15)
            print(f"    [{label}] Direct(session): HTTP {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0:
                    print(f"    [{label}] ✅ Direct(session) succeeded!")
                    return data
                else:
                    print(f"    [{label}] API code={data.get('code')}, msg={data.get('msg','?')}")
                    data = None
        except Exception as e:
            print(f"    [{label}] Direct(session) error: {e}")
    
    # ── Method 2: Direct with Cookie header ──
    if cookies_str and data is None:
        try:
            req_headers = headers.copy()
            req_headers['Cookie'] = cookies_str
            resp = requests.get(full_url, headers=req_headers, timeout=15)
            print(f"    [{label}] Direct(cookie): HTTP {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0:
                    print(f"    [{label}] ✅ Direct(cookie) succeeded!")
                    return data
                else:
                    print(f"    [{label}] API code={data.get('code')}, msg={data.get('msg','?')}")
                    data = None
            else:
                print(f"    [{label}] Response: {resp.text[:200]}")
        except Exception as e:
            print(f"    [{label}] Direct(cookie) error: {e}")
    
    # ── Method 3: Proxy fallback ──
    if data is None:
        try:
            from shopee_proxy import proxy_get_json, is_proxy_available
            if is_proxy_available():
                print(f"    [{label}] Trying proxy...")
                status, data = proxy_get_json(full_url, headers=headers,
                                              cookies_str=cookies_str)
                print(f"    [{label}] Proxy: HTTP {status}")
                if status == 200 and data and data.get('code') == 0:
                    print(f"    [{label}] ✅ Proxy succeeded!")
                    return data
                else:
                    preview = str(data)[:200] if data else 'empty'
                    print(f"    [{label}] Proxy response: {preview}")
                    data = None
        except ImportError:
            pass
        except Exception as e:
            print(f"    [{label}] Proxy error: {e}")
    
    return None


# ═══════════════════════════════════════════════════════════════════
#  STEP 1: GET SHOPS FROM AFFILIATE DASHBOARD API
# ═══════════════════════════════════════════════════════════════════
def get_affiliate_shops(keyword, session=None, limit=20):
    """Fetch shop offers from Shopee Affiliate Dashboard API.
    Endpoint: /api/v3/offer/shop/list"""
    url = f"{AFFILIATE_BASE}/api/v3/offer/shop/list"
    params = {
        'sort_type': 1,
        'page_offset': 0,
        'page_limit': limit,
        'keyword': keyword,
    }

    try:
        data = _make_affiliate_request(url, params, session=session,
                                        label=f'Shops/{keyword}')
        if not data:
            print(f"    [Affiliate] No valid data for '{keyword}'")
            return []

        shops = data.get('data', {}).get('list', [])
        total = data.get('data', {}).get('total_count', 0)
        print(f"    [Affiliate] '{keyword}' → {len(shops)} shops (total {total})")
        return shops

    except Exception as e:
        import traceback
        print(f"    [Affiliate] Exception: {e}")
        traceback.print_exc()
        return []


# ═══════════════════════════════════════════════════════════════════
#  STEP 1B: GET PRODUCT OFFERS (Penawaran Produk tab)
# ═══════════════════════════════════════════════════════════════════
def get_affiliate_product_offers(keyword, session=None, limit=20):
    """Fetch product offers from Shopee Affiliate Dashboard API.
    Endpoint: /api/v3/offer/product/list (Penawaran Produk tab)"""
    url = f"{AFFILIATE_BASE}/api/v3/offer/product/list"
    params = {
        'sort_type': 1,
        'page_offset': 0,
        'page_limit': limit,
        'keyword': keyword,
    }

    try:
        data = _make_affiliate_request(url, params, session=session,
                                        label=f'ProductOffer/{keyword}')
        if not data:
            print(f"    [ProductOffer] No data for '{keyword}'")
            return []

        products = data.get('data', {}).get('list', [])
        total = data.get('data', {}).get('total_count', 0)
        print(f"    [ProductOffer] '{keyword}' → {len(products)} products (total {total})")
        return products

    except Exception as e:
        import traceback
        print(f"    [ProductOffer] Exception: {e}")
        traceback.print_exc()
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
      1. Check if auto-login pre-fetched products (from Playwright browser)
      2. If not, try HTTP API calls (may fail due to anti-bot)
      3. Return product list ready for bank storage
      
    Returns: list of dicts with nama, price, image_url, shopee_url, source, commission
    """
    print(f"\n  === Affiliate API: {category} (target={target}) ===")
    
    # ── Check for pre-fetched products from auto-login (Playwright) ──
    prefetch_file = '/tmp/affiliate_products.json'
    try:
        if os.path.exists(prefetch_file):
            with open(prefetch_file, 'r') as f:
                prefetched = json.load(f)
            
            products_raw = prefetched.get(category, [])
            if products_raw:
                print(f"  ✅ Found {len(products_raw)} pre-fetched products (via Playwright)")
                
                all_products = []
                for po in products_raw[:target]:
                    # Shopee API structure:
                    #   Top level: item_id, long_link, product_link, commission_rate, ...
                    #   Nested:    batch_item_for_item_card_full → name, image, price, shopid, ...
                    item_data = po.get('batch_item_for_item_card_full', {}) or {}
                    
                    # Extract name from nested item data
                    product_name = (
                        item_data.get('name') or item_data.get('item_name') or
                        item_data.get('title') or
                        po.get('product_name') or po.get('item_name') or po.get('name') or ''
                    )
                    
                    # Extract image from nested item data
                    raw_image = (
                        item_data.get('image') or item_data.get('item_image') or
                        po.get('product_image') or po.get('image') or ''
                    )
                    if raw_image and not raw_image.startswith('http'):
                        product_image = f"https://down-id.img.susercontent.com/file/{raw_image}"
                    else:
                        product_image = raw_image
                    
                    # Extract price from nested item data (Shopee prices are in units * 100000)
                    raw_price = (
                        item_data.get('price') or item_data.get('price_min') or
                        po.get('price') or 0
                    )
                    if isinstance(raw_price, (int, float)) and raw_price > 100000:
                        item_price = raw_price / 100000  # Convert from Shopee price units
                    else:
                        item_price = raw_price
                    
                    # Top-level fields
                    product_link = po.get('long_link') or po.get('product_link') or ''
                    commission = (
                        po.get('seller_commission_rate') or po.get('max_commission_rate') or
                        po.get('default_commission_rate') or po.get('commission_rate') or '0%'
                    )
                    shop_name = (
                        item_data.get('shop_name') or item_data.get('seller_name') or
                        po.get('shop_name') or ''
                    )
                    
                    if not product_name:
                        continue
                    
                    all_products.append({
                        'nama': product_name[:80],
                        'price': f"Rp{int(item_price):,}".replace(',', '.') if isinstance(item_price, (int, float)) and item_price > 0 else 'Lihat harga',
                        'desc': product_name,
                        'image_url': product_image,
                        'shopee_url': product_link,
                        'source': 'shopee_affiliate_product',
                        'commission': commission,
                        'shop_name': shop_name,
                    })
                
                print(f"  → Pre-fetched: {len(all_products)} products for {category}")
                if all_products:
                    print(f"    Sample: {all_products[0]['nama'][:50]} | img={'YES' if all_products[0]['image_url'] else 'NO'}")
                elif products_raw:
                    sample = products_raw[0]
                    nested = sample.get('batch_item_for_item_card_full', {})
                    print(f"  [DEBUG] Nested keys: {list(nested.keys()) if isinstance(nested, dict) else type(nested)}")
                return all_products
            else:
                print(f"  ⚠️ Pre-fetch file exists but no products for '{category}'")
    except Exception as e:
        print(f"  ⚠️ Pre-fetch read error: {e}")
    
    # ── Fallback: HTTP requests (for local dev, may fail in CI) ──
    print(f"  [Fallback] Trying HTTP API calls...")
    session = _build_affiliate_session()

    keywords = AFFILIATE_KEYWORDS.get(category, [category])
    random.shuffle(keywords)
    selected_keywords = keywords[:3]

    all_products = []

    for keyword in selected_keywords:
        if len(all_products) >= target:
            break

        # ───────────────────────────────────────────────────────
        #  STEP A: Product Offer API (Penawaran Produk — direct)
        # ───────────────────────────────────────────────────────
        print(f"\n  [A] Product offers: '{keyword}'...")
        time.sleep(random.uniform(1.0, 2.0))

        prod_offers = get_affiliate_product_offers(keyword, session=session, limit=10)
        for po in prod_offers:
            if len(all_products) >= target:
                break
            # Product offer response has different field names
            product_name = po.get('product_name', po.get('item_name', ''))
            product_image = po.get('product_image', po.get('image', ''))
            product_link = po.get('long_link', po.get('product_link', ''))
            commission = po.get('commission_rate', '0%')
            item_price = po.get('price', po.get('product_price', 0))
            shop_name = po.get('shop_name', '')

            if not product_name:
                continue

            # Build image URL from hash if needed
            if product_image and not product_image.startswith('http'):
                product_image = f"https://down-id.img.susercontent.com/file/{product_image}"

            all_products.append({
                'nama': product_name[:80],
                'price': f"Rp{item_price:,}".replace(',', '.') if isinstance(item_price, (int, float)) and item_price > 0 else 'Lihat harga',
                'desc': product_name,
                'image_url': product_image,
                'shopee_url': product_link,
                'source': 'shopee_affiliate_product',
                'commission': commission,
                'shop_name': shop_name,
            })
            print(f"      ✓ [ProductOffer] {product_name[:40]}")

        if len(all_products) >= target:
            break

        # ───────────────────────────────────────────────────────
        #  STEP B: Shop Offer API (Komisi XTRA — shop→products)
        # ───────────────────────────────────────────────────────
        print(f"\n  [B] Shop offers: '{keyword}'...")
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
