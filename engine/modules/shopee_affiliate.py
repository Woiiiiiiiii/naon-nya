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
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json',
        'Referer': f'{AFFILIATE_BASE}/offer/brand_offer',
        'Origin': AFFILIATE_BASE,
    }
    # Add CSRF token (required for authenticated API calls)
    csrf = _get_csrftoken()
    if csrf:
        headers['x-csrftoken'] = csrf
    cookies_str = _build_cookie_string()

    try:
        from shopee_proxy import proxy_get_json, is_proxy_available
        if is_proxy_available():
            full_url = f"{url}?{urlencode(params)}"
            status, data = proxy_get_json(full_url, headers=headers,
                                          cookies_str=cookies_str)
            if status == 200 and data and data.get('code') == 0:
                print("  ✅ Affiliate cookies are VALID")
                _COOKIES_VALID = True
                return True
            else:
                code = data.get('code', '?') if data else '?'
                msg = data.get('msg', '?') if data else f'HTTP {status}'
                print(f"  ❌ Affiliate cookies REJECTED: code={code}, msg={msg}")
                if code == 30002:
                    print("  ⚠️  Cookies expired! Re-export from affiliate.shopee.co.id")
                _COOKIES_VALID = False
                return False
    except ImportError:
        pass

    # Try direct
    try:
        req_headers = headers.copy()
        req_headers['Cookie'] = cookies_str
        full_url = f"{url}?{urlencode(params)}"
        resp = requests.get(full_url, headers=req_headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 0:
                print("  ✅ Affiliate cookies are VALID (direct)")
                _COOKIES_VALID = True
                return True
            else:
                print(f"  ❌ Cookies REJECTED: code={data.get('code')}, msg={data.get('msg')}")
                _COOKIES_VALID = False
                return False
    except Exception as e:
        print(f"  [Health] Check failed: {e}")

    _COOKIES_VALID = None  # Unknown
    return True  # Optimistic default


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
    """Build cookie string from env for proxy requests.
    Only includes cookies from Shopee-related domains."""
    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not cookies_raw:
        return ''
    try:
        cookies = json.loads(cookies_raw)
        if isinstance(cookies, list):
            # Filter: only include cookies from Shopee domains
            shopee_cookies = []
            for c in cookies:
                domain = c.get('domain', '')
                name = c.get('name', '')
                value = c.get('value', '')
                if not name or not value:
                    continue
                # Only include Shopee-related cookies
                if 'shopee' in domain.lower():
                    shopee_cookies.append(f"{name}={value}")
            return '; '.join(shopee_cookies)
        elif isinstance(cookies, dict):
            return '; '.join([f'{k}={v}' for k, v in cookies.items()])
    except Exception:
        pass
    return ''


def _get_csrftoken():
    """Extract csrftoken value from cookies for x-csrftoken header.
    Shopee affiliate API requires this header for authenticated requests."""
    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not cookies_raw:
        return ''
    try:
        cookies = json.loads(cookies_raw)
        if isinstance(cookies, list):
            for c in cookies:
                if c.get('name') == 'csrftoken':
                    return c.get('value', '')
        elif isinstance(cookies, dict):
            return cookies.get('csrftoken', '')
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
        'Referer': f'{AFFILIATE_BASE}/offer/brand_offer',
        'Origin': AFFILIATE_BASE,
        'X-Requested-With': 'XMLHttpRequest',
    }

    # Add CSRF token header (required by Shopee for authenticated API calls)
    csrf = _get_csrftoken()
    if csrf:
        headers['x-csrftoken'] = csrf
        print(f"    [Affiliate] CSRF token: {csrf[:10]}...")
    else:
        print("    [Affiliate] ⚠️ No csrftoken found in cookies!")

    try:
        # Try via proxy first (GitHub Actions IP is in US → blocked without proxy)
        data = None
        cookies_str = _build_cookie_string()
        print(f"    [Affiliate] Cookies: {len(cookies_str)} chars")

        try:
            from shopee_proxy import proxy_get_json, is_proxy_available
            if is_proxy_available():
                full_url = f"{url}?{urlencode(params)}"
                print(f"    [Affiliate] Trying proxy → {full_url[:80]}...")
                status, data = proxy_get_json(full_url, headers=headers,
                                              cookies_str=cookies_str)
                print(f"    [Affiliate] Proxy response: HTTP {status}")
                if status != 200:
                    # Show response preview for debugging
                    preview = str(data)[:200] if data else 'empty'
                    print(f"    [Affiliate] Response preview: {preview}")
                    data = None
                elif data and data.get('code') != 0:
                    print(f"    [Affiliate] Proxy API code={data.get('code')}, msg={data.get('msg', '?')}")
                    data = None
            else:
                print("    [Affiliate] Proxy not available")
        except ImportError:
            print("    [Affiliate] shopee_proxy module not found")

        # Direct request fallback (works if running locally or from Indonesian IP)
        if data is None:
            if session:
                print(f"    [Affiliate] Trying direct request...")
                resp = session.get(url, params=params, timeout=15)
                print(f"    [Affiliate] Direct response: HTTP {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('code') != 0:
                        print(f"    [Affiliate] Direct API code={data.get('code')}, msg={data.get('msg', '?')}")
                        data = None
                else:
                    print(f"    [Affiliate] Direct failed: {resp.text[:200]}")
            elif cookies_str:
                # No session but have cookies — try direct with cookie header
                print(f"    [Affiliate] Trying direct with cookie header...")
                full_url = f"{url}?{urlencode(params)}"
                req_headers = headers.copy()
                req_headers['Cookie'] = cookies_str
                resp = requests.get(full_url, headers=req_headers, timeout=15)
                print(f"    [Affiliate] Direct+cookies response: HTTP {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('code') != 0:
                        print(f"    [Affiliate] API code={data.get('code')}, msg={data.get('msg', '?')}")
                        data = None
            else:
                print("    [Affiliate] No session and no cookies — cannot make request")

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

    Endpoint: /api/v3/offer/product/list  (Penawaran Produk tab)
    Returns individual products with affiliate links, prices, images.

    This is DIFFERENT from shop/list — gives actual products, not shops.
    Each product has: item_id, shop_id, product_name, image, price,
    commission_rate, and long_link (affiliate URL).
    """
    url = f"{AFFILIATE_BASE}/api/v3/offer/product/list"
    params = {
        'sort_type': 1,
        'page_offset': 0,
        'page_limit': limit,
        'keyword': keyword,
    }

    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json',
        'Referer': f'{AFFILIATE_BASE}/offer/brand_offer',
        'Origin': AFFILIATE_BASE,
        'X-Requested-With': 'XMLHttpRequest',
    }

    try:
        data = None
        cookies_str = _build_cookie_string()

        # Try via proxy first (GitHub Actions = US IP → needs proxy)
        try:
            from shopee_proxy import proxy_get_json, is_proxy_available
            if is_proxy_available():
                full_url = f"{url}?{urlencode(params)}"
                print(f"    [ProductOffer] Proxy → {full_url[:80]}...")
                status, data = proxy_get_json(full_url, headers=headers,
                                              cookies_str=cookies_str)
                print(f"    [ProductOffer] Proxy HTTP {status}")
                if status != 200:
                    preview = str(data)[:200] if data else 'empty'
                    print(f"    [ProductOffer] Preview: {preview}")
                    data = None
                elif data and data.get('code') != 0:
                    print(f"    [ProductOffer] API code={data.get('code')}, msg={data.get('msg','?')}")
                    data = None
            else:
                print("    [ProductOffer] Proxy not available")
        except ImportError:
            print("    [ProductOffer] shopee_proxy not found")

        # Direct request fallback
        if data is None:
            if session:
                resp = session.get(url, params=params, timeout=15)
                print(f"    [ProductOffer] Direct HTTP {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('code') != 0:
                        print(f"    [ProductOffer] API code={data.get('code')}")
                        data = None
            elif cookies_str:
                full_url = f"{url}?{urlencode(params)}"
                req_headers = headers.copy()
                req_headers['Cookie'] = cookies_str
                resp = requests.get(full_url, headers=req_headers, timeout=15)
                print(f"    [ProductOffer] Direct+cookies HTTP {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('code') != 0:
                        data = None

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
      1. Try product offer API (/api/v3/offer/product/list) → direct products
      2. Try shop offer API (/api/v3/offer/shop/list) → shops → products
      3. Build affiliate links for each product
      4. Return product list ready for bank storage
      
    Returns: list of dicts with nama, price, image_url, shopee_url, source, commission
    """
    print(f"\n  === Affiliate API: {category} (target={target}) ===")
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
