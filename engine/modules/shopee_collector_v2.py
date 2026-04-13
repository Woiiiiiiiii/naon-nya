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
from urllib.parse import unquote, urlencode

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
AFFILIATE_BASE = 'https://affiliate.shopee.co.id'
SHOPEE_BASE = 'https://shopee.co.id'
BANK_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'product_bank')
TARGET_PER_CATEGORY = 25

CATEGORIES = {
    'fashion': [
        'tas selempang', 'sepatu sneakers', 'jam tangan pria', 'dompet kulit',
        'topi bucket hat', 'kacamata hitam', 'gelang titanium', 'ikat pinggang',
        'jaket hoodie', 'kaos polos premium', 'celana cargo', 'sandal slide',
        'backpack ransel', 'sling bag wanita', 'tote bag kanvas',
        'kemeja flannel', 'cardigan rajut', 'cincin couple', 'anting mutiara',
        'scarf satin', 'dress casual', 'rok plisket', 'celana kulot',
        'sepatu boots', 'tas pinggang',
    ],
    'gadget': [
        'earphone bluetooth', 'powerbank fast charging', 'smartwatch murah',
        'TWS wireless', 'mouse wireless', 'keyboard mechanical', 'USB hub',
        'ring light selfie', 'phone holder', 'speaker bluetooth mini',
        'charger fast charging', 'kabel data type C', 'tripod hp',
        'webcam HD', 'flash drive 64GB', 'cooling pad laptop',
        'headset gaming', 'smart plug wifi', 'card reader', 'gimbal hp',
        'screen protector', 'tablet stand', 'LED strip', 'MiFi portable',
        'action camera mini',
    ],
    'beauty': [
        'skincare korea', 'serum vitamin C', 'sunscreen SPF 50', 'moisturizer',
        'toner wajah', 'lip tint', 'mascara waterproof', 'foundation cushion',
        'bedak tabur', 'micellar water', 'eye cream', 'sheet mask',
        'body lotion', 'parfum wanita', 'sabun muka', 'blush on',
        'concealer', 'setting spray', 'lip balm', 'hair serum',
        'vitamin rambut', 'beauty blender', 'brush makeup set',
        'nail art set', 'eyeliner pen',
    ],
    'home': [
        'lampu tidur LED', 'organizer laci', 'vacuum cleaner mini',
        'rak buku kayu', 'dispenser sabun', 'gantungan baju', 'kotak penyimpanan',
        'jam dinding minimalis', 'bantal sofa', 'karpet bulu', 'teko listrik',
        'tempat tissue', 'pot tanaman hias', 'cermin rias', 'selimut fleece',
        'sarung bantal', 'tirai kamar', 'humidifier', 'air purifier',
        'set alat makan', 'panci set', 'wajan anti lengket', 'talenan kayu',
        'pisau dapur set', 'blender mini portable',
    ],
    'wellness': [
        'vitamin C 1000mg', 'botol minum tumbler', 'alat olahraga rumah',
        'matras yoga', 'resistance band', 'skipping rope adjustable',
        'dumbbell set', 'hand grip', 'shaker protein', 'masker KN95',
        'termometer digital', 'tensimeter digital', 'essential oil',
        'diffuser aromaterapi', 'alat pijat elektrik', 'posture corrector',
        'knee support', 'foam roller', 'sarung tangan gym', 'kaos olahraga',
        'celana training', 'timbangan badan digital', 'suplemen fitness',
        'koyo pereda nyeri', 'kacamata anti blue light',
    ],
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
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': f'{AFFILIATE_BASE}/offer/brand_offer',
        'Origin': AFFILIATE_BASE,
        'Connection': 'keep-alive',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
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
#  Priority: Browser fetch → Direct → CF Proxy
# ═══════════════════════════════════════════════════════════════════
_browser_ctx = None
_browser_page = None
_pw_instance = None

# Full stealth init script
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {} };
const origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (params) =>
  params.name === 'notifications'
    ? Promise.resolve({state: Notification.permission})
    : origQuery(params);
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['id-ID','id','en-US','en']});
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
"""


def _init_browser(cookie_str):
    """Buka browser stealth + inject cookies + auto-export fresh cookies.
    
    Implements anti-block strategy:
    - domcontentloaded (no networkidle hang)
    - Block heavy resources (faster + less suspicious)
    - Warm-up via shopee.co.id first (more human-like)
    - Content-based block detection
    - Random delays
    """
    global _browser_ctx, _browser_page, _pw_instance
    if _browser_page:
        return True

    if not HAS_PLAYWRIGHT:
        return False

    try:
        _pw_instance = sync_playwright().start()
        browser = _pw_instance.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-infobars',
                '--window-size=1366,768',
            ]
        )
        _browser_ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1366, 'height': 768},
            locale='id-ID',
            timezone_id='Asia/Jakarta',
            extra_http_headers={
                'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
            }
        )
        _browser_ctx.add_init_script(STEALTH_JS)

        # Inject cookies
        pw_cookies = []
        for pair in cookie_str.split('; '):
            if '=' in pair:
                name, _, value = pair.partition('=')
                if name and value:
                    pw_cookies.append({
                        'name': name, 'value': value,
                        'domain': '.shopee.co.id', 'path': '/'
                    })
        _browser_ctx.add_cookies(pw_cookies)
        print(f"      Browser: {len(pw_cookies)} cookies injected")

        page = _browser_ctx.new_page()

        # FIX 6: Block heavy resources (faster + less bot-like)
        def _block_heavy(route):
            if route.request.resource_type in ['image', 'media', 'font', 'stylesheet']:
                route.abort()
            else:
                route.continue_()
        page.route('**/*', _block_heavy)

        # FIX 8: Warm-up — visit shopee.co.id first (more human-like flow)
        print("      Browser: warm-up via shopee.co.id...")
        try:
            page.goto('https://shopee.co.id', timeout=15000, wait_until='domcontentloaded')
        except Exception:
            print("      Browser: warm-up timeout (OK, continuing)")

        # FIX 4: Random delay (human-like)
        time.sleep(random.uniform(3, 5))

        # FIX 1+2: Navigate with domcontentloaded + fail fast
        print("      Browser: navigating to affiliate page...")
        try:
            page.goto('https://affiliate.shopee.co.id/offer/brand_offer',
                      timeout=30000, wait_until='domcontentloaded')
        except Exception as e:
            print(f"      Browser: nav failed: {str(e)[:60]}")
            print("      Browser: ❌ Kemungkinan IP diblock")
            browser.close()
            _pw_instance.stop()
            _browser_page = None
            return False

        # Wait for page to SETTLE (Shopee JS does redirects after DOM load)
        # Short timeout — if it hangs, page is probably blocked
        print("      Browser: waiting for page to settle...")
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
            print("      Browser: page settled (networkidle)")
        except Exception:
            print("      Browser: settle timeout (20s) — continuing anyway")

        # FIX 4: Random delay after load
        time.sleep(random.uniform(2, 4))

        # FIX 3: Detect block via URL + page content
        current_url = page.url
        print(f"      Browser: on {current_url[:80]}")

        if 'captcha' in current_url or 'verify' in current_url:
            print("      Browser: ❌ CAPTCHA — IP blocked")
            browser.close()
            _pw_instance.stop()
            _browser_page = None
            return False

        # FIX 3: Content-based block detection
        try:
            content = page.content().lower()
            if 'captcha' in content or 'access denied' in content or 'forbidden' in content:
                print("      Browser: ❌ Block detected in page content")
                browser.close()
                _pw_instance.stop()
                _browser_page = None
                return False
        except Exception:
            pass

        # Auto-export refreshed cookies
        _export_browser_cookies()

        # Test API (with AbortController timeout to prevent hang)
        print("      Browser: testing API...")
        try:
            test = page.evaluate("""
                async () => {
                    const ctrl = new AbortController();
                    setTimeout(() => ctrl.abort(), 10000);
                    try {
                        const r = await fetch(
                            "/api/v3/offer/product/list?list_type=5&sort_type=5&page_offset=0&page_limit=1&client_type=1",
                            {headers: {"Accept": "application/json"}, signal: ctrl.signal}
                        );
                        const data = await r.json();
                        return {status: r.status, code: data.code, error: data.error,
                                count: (data.data && data.data.list) ? data.data.list.length : 0};
                    } catch(e) { return {error: e.message}; }
                }
            """)
        except Exception as e:
            print(f"      Browser: API test timeout: {str(e)[:60]}")
            test = {'error': 'timeout'}
        print(f"      Browser: test = {test}")

        _browser_page = page
        if test and test.get('code') == 0:
            print("      Browser: ✅ API works!")
        else:
            print("      Browser: ⚠️ API test failed, will try direct HTTP")
        return True

    except Exception as e:
        print(f"      Browser init error: {e}")
        _browser_page = None
        return False


def _export_browser_cookies():
    """Export cookies from browser → cache + GH secret.
    Browser auto-refreshes session tokens on navigation.
    """
    if not _browser_ctx:
        return
    try:
        cookies = _browser_ctx.cookies()
        shopee_cookies = [
            {'name': c['name'], 'value': c['value'],
             'domain': c.get('domain', '.shopee.co.id'),
             'path': c.get('path', '/')}
            for c in cookies if 'shopee' in c.get('domain', '')
        ]
        if not shopee_cookies:
            return

        refreshed_json = json.dumps(shopee_cookies, ensure_ascii=False)
        print(f"      Browser: exported {len(shopee_cookies)} cookies")

        # Save to cache
        try:
            with open('/tmp/.shopee_cookies.json', 'w') as f:
                f.write(refreshed_json)
            with open('/tmp/.cookies_session_valid', 'w') as f:
                f.write('1')
        except Exception:
            pass

        # Update GITHUB_ENV
        github_env = os.environ.get('GITHUB_ENV', '')
        if github_env:
            try:
                with open(github_env, 'a') as f:
                    f.write(f"SHOPEE_AFFILIATE_COOKIES<<EOF\n{refreshed_json}\nEOF\n")
                print("      Browser: cookies → GITHUB_ENV")
            except Exception:
                pass

        # Update GH secret
        import subprocess
        gh_token = os.environ.get('GH_TOKEN', '')
        if gh_token:
            try:
                result = subprocess.run(
                    ['gh', 'secret', 'set', 'SHOPEE_AFFILIATE_COOKIES'],
                    input=refreshed_json, capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    print("      Browser: ✅ GH secret updated!")
            except Exception:
                pass
    except Exception as e:
        print(f"      Browser: cookie export error: {e}")


def _browser_fetch(keyword, page_offset=0, page_limit=20):
    """STEP 2: Fetch affiliate product list VIA browser (bypass anti-bot).
    
    browser.evaluate(fetch()) runs in real browser context:
    - Same-origin → no CORS
    - Cookies auto-included
    - Anti-bot JS tokens auto-generated by Shopee's own JS
    
    Ini PERSIS sama dengan: buka dashboard → klik request → copy dari browser.
    """
    if not _browser_page:
        return None

    try:
        params = urlencode({
            'list_type': 5, 'sort_type': 5,
            'page_offset': page_offset, 'page_limit': page_limit,
            'client_type': 1, 'keyword': keyword,
        })
        result = _browser_page.evaluate("""
            async (queryString) => {
                const ctrl = new AbortController();
                setTimeout(() => ctrl.abort(), 10000);
                try {
                    const resp = await fetch(
                        "/api/v3/offer/product/list?" + queryString,
                        {headers: {"Accept": "application/json"}, signal: ctrl.signal}
                    );
                    if (!resp.ok) return {error: resp.status};
                    return await resp.json();
                } catch(e) { return {error: e.message}; }
            }
        """, params)
        return result
    except Exception as e:
        print(f"      Browser fetch error: {e}")
        return None


# Persistent session for more human-like flow
_http_session = None

def _get_session(headers):
    """Get or create a persistent requests.Session."""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        _http_session.headers.update({
            k: v for k, v in headers.items() if k != 'Cookie'
        })
        # Warm-up: visit shopee.co.id first (get initial cookies)
        print("  \U0001f310 HTTP warm-up: visiting shopee.co.id...")
        try:
            _http_session.get('https://shopee.co.id/', timeout=10)
            time.sleep(random.uniform(1, 3))
            print("  \u2705 HTTP warm-up done")
        except Exception:
            print("  \u26a0\ufe0f HTTP warm-up failed (continuing)")
    return _http_session


def _api_get_direct(url, params, headers, cookie_str):
    """Fallback: Direct HTTP (with Session + retry) + CF Proxy."""
    full_url = f"{url}?{urlencode(params)}"
    session = _get_session(headers)

    # Direct with retry on 403
    for attempt in range(3):
        try:
            resp = session.get(full_url, headers={'Cookie': cookie_str}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0:
                    return data
                print(f"      Direct: error {data.get('error', data.get('code'))}")
                break  # Got response but wrong code, don't retry
            elif resp.status_code == 403:
                if attempt < 2:
                    delay = 8 + attempt * 5  # 8s, 13s
                    print(f"      Direct: HTTP 403 (retry {attempt+1}/3, wait {delay}s...)")
                    time.sleep(delay)
                else:
                    print(f"      Direct: HTTP 403 (all 3 retries failed)")
            else:
                print(f"      Direct: HTTP {resp.status_code}")
                break
        except Exception as e:
            print(f"      Direct: {e}")
            break

    # CF Proxy
    try:
        from shopee_proxy import proxy_get_json, is_proxy_available
        if is_proxy_available():
            proxy_h = {k: v for k, v in headers.items() if k != 'Cookie'}
            status, data = proxy_get_json(full_url, headers=proxy_h, cookies_str=cookie_str)
            if status == 200 and data and data.get('code') == 0:
                return data
            err = data.get('error', '?') if data else '?'
            print(f"      Proxy: HTTP {status}, error={err}")
    except ImportError:
        pass
    except Exception as e:
        print(f"      Proxy: {e}")

    return None


def get_products_by_keyword(headers, cookie_str, keyword, target=25, use_browser=False):
    """STEP 2-5: Hit affiliate API with keyword, paginate sampai target."""
    products = []
    page = 0
    page_size = 10  # Smaller batch = less suspicious

    while len(products) < target:
        data = None
        offset = page * page_size

        # Try browser first (if available)
        if use_browser and _browser_page:
            result = _browser_fetch(keyword, page_offset=offset, page_limit=page_size)
            if result and result.get('code') == 0:
                data = result
            elif result:
                err = result.get('error', '?')
                print(f"      Browser: error={err}")

        # Fallback to direct + proxy
        if not data:
            url = f"{AFFILIATE_BASE}/api/v3/offer/product/list"
            params = {
                'list_type': 5, 'sort_type': 5,
                'page_offset': offset, 'page_limit': page_size,
                'client_type': 1, 'keyword': keyword,
            }
            data = _api_get_direct(url, params, headers, cookie_str)

        if not data:
            break

        items = data.get('data', {}).get('list', [])
        if not items:
            break

        products.extend(items)
        page += 1
        # Shorter delay when browser works, longer for direct HTTP
        if use_browser and _browser_page:
            time.sleep(random.uniform(0.5, 1.5))
        else:
            time.sleep(random.uniform(2, 4))

    return products[:target]


# ═══════════════════════════════════════════════════════════════════
#  STEP 6: EXTRACT item_id & shop_id
# ═══════════════════════════════════════════════════════════════════
def extract_ids(offer):
    """STEP 6: Ambil item_id + shop_id dari response."""
    item_id = (
        offer.get('item_id') or offer.get('itemid') or
        offer.get('product_id') or offer.get('id') or 0
    )
    shop_id = (
        offer.get('shop_id') or offer.get('shopid') or 0
    )

    # Coba dari nested
    for nested_key in ['batch_item_for_item_card_full', 'item', 'product']:
        nested = offer.get(nested_key, {})
        if isinstance(nested, dict):
            item_id = item_id or nested.get('itemid', 0) or nested.get('item_id', 0)
            shop_id = shop_id or nested.get('shopid', 0) or nested.get('shop_id', 0)

    # Coba dari product_link / long_link / offer_link
    if not item_id or not shop_id:
        for link_key in ['product_link', 'long_link', 'offer_link', 'link']:
            link = offer.get(link_key, '')
            if '/product/' in str(link):
                parts = str(link).split('/product/')[-1].split('?')[0].split('/')
                if len(parts) >= 2:
                    try:
                        shop_id = shop_id or int(parts[0])
                        item_id = item_id or int(parts[1])
                    except ValueError:
                        pass
                break

    # Convert to int
    try:
        item_id = int(item_id) if item_id else 0
        shop_id = int(shop_id) if shop_id else 0
    except (ValueError, TypeError):
        item_id, shop_id = 0, 0

    return item_id, shop_id


# ═══════════════════════════════════════════════════════════════════
#  STEP 7: GET product detail — name, price, images
#  Priority: extract from offer → CF Proxy → Direct HTTP
# ═══════════════════════════════════════════════════════════════════
def _extract_from_offer(offer):
    """Try to extract product detail directly from affiliate API response.
    
    The affiliate API already returns `batch_item_for_item_card_full`
    which contains name, price, and image hash — no need for second request!
    """
    nested = offer.get('batch_item_for_item_card_full', {})
    if not isinstance(nested, dict):
        return None

    name = nested.get('name', '')
    if not name:
        return None

    # Price (may be string from API)
    try:
        price = int(nested.get('price_max', 0) or nested.get('price', 0) or 0)
    except (ValueError, TypeError):
        price = 0
    if price > 10000000:
        price = price // 100000

    # Image
    image = nested.get('image', '')
    images = nested.get('images', [])
    img_hash = images[0] if images else image
    if not img_hash:
        return None

    return {
        'name': name,
        'price': price,
        'image_hash': img_hash,
        'image_url': f"https://cf.shopee.co.id/file/{img_hash}",
        'all_image_hashes': images if images else [image] if image else [],
    }


def get_product_detail(item_id, shop_id, offer=None):
    """STEP 7: Get name + price + images.
    
    Priority:
    1. Extract from offer response (no extra request needed!)
    2. CF Proxy → shopee.co.id/api/v4/item/get
    3. Direct HTTP (will fail from GH Actions)
    """
    # 1. Try from offer data first
    if offer:
        detail = _extract_from_offer(offer)
        if detail:
            return detail

    url = f"{SHOPEE_BASE}/api/v4/item/get"
    params = {'itemid': item_id, 'shopid': shop_id}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': f'{SHOPEE_BASE}/product/{shop_id}/{item_id}',
        'X-Shopee-Language': 'id',
    }

    # 2. Try CF Proxy
    try:
        from shopee_proxy import proxy_get_json, is_proxy_available
        if is_proxy_available():
            full_url = f"{url}?itemid={item_id}&shopid={shop_id}"
            status, data = proxy_get_json(full_url, headers=headers, cookies_str='')
            if status == 200 and data:
                item = data.get('data', data.get('item', {}))
                if item and item.get('name'):
                    return _parse_item_detail(item)
    except ImportError:
        pass
    except Exception:
        pass

    # 3. Direct HTTP (last resort)
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            item = data.get('data', data.get('item', {}))
            if item and item.get('name'):
                return _parse_item_detail(item)
    except Exception:
        pass

    return None


def _parse_item_detail(item):
    """Parse item from /api/v4/item/get response."""
    price = item.get('price', 0)
    if price > 10000000:
        price = price // 100000

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
        'all_image_hashes': images if images else [image] if image else [],
    }


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════
def _load_used_ids():
    """Load product IDs already used in videos from used_products.json.
    Products here will NEVER be re-downloaded — saves bandwidth & storage.
    """
    used_file = os.path.join(os.path.dirname(__file__), '..', 'state', 'used_products.json')
    if not os.path.exists(used_file):
        return set()
    try:
        with open(used_file, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        # Collect all product IDs across all accounts
        used = set()
        for acct_data in data.values():
            if isinstance(acct_data, dict):
                used.update(acct_data.keys())
        return used
    except Exception:
        return set()


def _gen_id(name, cat):
    return hashlib.md5(f"{cat}_{name}".lower().encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════════════
#  IMAGE QUALITY GATE — only high-quality seller images enter bank
# ═══════════════════════════════════════════════════════════════════
MIN_IMAGE_SIZE = 500       # Minimum 500×500 pixels
MIN_ASPECT_RATIO = 0.3     # Reject extremely narrow images
MAX_ASPECT_RATIO = 3.0     # Reject extremely tall images
MIN_CLEAN_SCORE = 25       # Minimum cleanliness score (text/watermark penalty)
MIN_BLUR_SCORE = 30        # Minimum sharpness (Laplacian variance)


def _score_image_quality(img):
    """Score image quality for product bank. Returns (score, reasons).

    Checks:
      - Resolution: min 500×500
      - Aspect ratio: 0.3 - 3.0 (reject extremely elongated)
      - Blur detection: Laplacian variance (reject blurry review photos)
      - Cleanliness: penalize text overlays, busy graphics, promo bands

    Returns: (total_score: float, reject_reasons: list[str])
      Score > 25 = acceptable for product bank
      Score < 25 = rejected (review photo, screenshot, or low quality)
    """
    import numpy as np
    w, h = img.size
    reasons = []
    score = 50.0

    # 1. Resolution check
    if w < MIN_IMAGE_SIZE or h < MIN_IMAGE_SIZE:
        reasons.append(f'too_small({w}x{h})')
        return 0, reasons

    # 2. Aspect ratio check
    ratio = w / h
    if ratio < MIN_ASPECT_RATIO or ratio > MAX_ASPECT_RATIO:
        reasons.append(f'bad_ratio({ratio:.2f})')
        return 0, reasons

    # 3. Blur detection (Laplacian variance)
    try:
        gray = img.convert('L')
        gray_arr = np.array(gray, dtype=np.float64)
        # Laplacian kernel approximation
        lap = (
            gray_arr[2:, 1:-1] + gray_arr[:-2, 1:-1] +
            gray_arr[1:-1, 2:] + gray_arr[1:-1, :-2] -
            4 * gray_arr[1:-1, 1:-1]
        )
        blur_var = lap.var()
        if blur_var < 5:
            reasons.append(f'very_blurry({blur_var:.0f})')
            return 0, reasons  # Immediate reject — completely blurry
        elif blur_var < MIN_BLUR_SCORE:
            reasons.append(f'blurry({blur_var:.0f})')
            score -= 45  # Heavy penalty
        elif blur_var > 200:
            score += 10  # Very sharp = good
    except Exception:
        pass

    # 4. Cleanliness score (adapted from download_images.py)
    try:
        data = np.array(img)

        # 4a. Edge density — high = lots of text/graphics
        brightness = data.mean(axis=2).astype(np.uint8)
        edge_h = np.abs(brightness[1:, :].astype(int) - brightness[:-1, :].astype(int))
        edge_v = np.abs(brightness[:, 1:].astype(int) - brightness[:, :-1].astype(int))
        edge_ratio = ((edge_h > 40).sum() + (edge_v > 40).sum()) / (h * w)

        if edge_ratio > 0.20:
            score -= 40
            reasons.append('text_heavy')
        elif edge_ratio > 0.12:
            score -= 25
            reasons.append('text_likely')
        elif edge_ratio < 0.04:
            score += 15  # Very clean

        # 4b. White/light background percentage
        white_pct = (brightness > 230).sum() / (h * w)
        score += white_pct * 30  # Clean white bg = good

        # 4c. Promo band detection — top/bottom 20%
        for band in [data[:h // 5, :, :], data[-h // 5:, :, :]]:
            band_edge = np.abs(band[1:, :, :].astype(int) - band[:-1, :, :].astype(int))
            if band_edge.mean() > 18:
                score -= 15
                reasons.append('promo_band')
                break

        # 4d. Border uniformity — uniform = clean product photo
        border = min(15, h // 20, w // 20)
        for strip in [data[:border], data[-border:], data[:, :border], data[:, -border:]]:
            if strip.std() < 15:
                score += 8  # Uniform border = clean bg
    except Exception:
        pass

    return round(max(0, score), 1), reasons


def _download_image(url, path):
    """Download image and validate quality before saving."""
    try:
        resp = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://shopee.co.id/',
        })
        if resp.status_code != 200 or len(resp.content) < 5000:
            return False

        from PIL import Image as PILImage
        from io import BytesIO
        img = PILImage.open(BytesIO(resp.content)).convert('RGB')

        # Quality gate
        score, reasons = _score_image_quality(img)
        if score < MIN_CLEAN_SCORE:
            return False

        img.save(path, 'JPEG', quality=95)
        return True
    except Exception:
        pass
    return False


# CDN fallback — cf.shopee.co.id may be blocked from GitHub Actions
_CDN_URLS = [
    'https://down-id.img.susercontent.com/file',
    'https://cf.shopee.co.id/file',
]
_IMG_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://shopee.co.id/',
}
_working_cdn = None  # Cache: once a CDN works, stick with it


def _try_download_image(img_hash):
    """Try downloading a single image hash from CDNs. Returns PIL Image or None."""
    global _working_cdn
    from PIL import Image as PILImage
    from io import BytesIO

    # If we already know which CDN works, try it first
    cdns = [_working_cdn] + [c for c in _CDN_URLS if c != _working_cdn] if _working_cdn else _CDN_URLS

    for cdn in cdns:
        try:
            resp = requests.get(f'{cdn}/{img_hash}', timeout=5, headers=_IMG_HEADERS)
            if resp.status_code == 200 and len(resp.content) >= 3000:
                _working_cdn = cdn  # Remember this CDN works!
                return PILImage.open(BytesIO(resp.content)).convert('RGB')
        except Exception:
            continue
    return None


def _download_best_image(image_hashes, path):
    """Download product image — fast strategy.

    Try max 3 images, take FIRST that passes QC.
    If none pass QC, save the first downloadable image anyway.

    Returns: (success: bool, score: float)
    """
    if not image_hashes:
        return False, 0

    first_img = None  # Fallback: first downloadable image

    for img_hash in image_hashes[:3]:  # Max 3 images only
        if not img_hash:
            continue
        img = _try_download_image(img_hash)
        if img is None:
            continue

        # Save first downloadable as fallback
        if first_img is None:
            first_img = img

        # QC check — take first that passes
        score, reasons = _score_image_quality(img)
        if score >= MIN_CLEAN_SCORE:
            img.save(path, 'JPEG', quality=95)
            return True, score

    # No image passed QC → save first downloadable anyway
    if first_img is not None:
        first_img.save(path, 'JPEG', quality=95)
        return True, 0

    return False, 0


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

    # Init browser for STEP 2 (affiliate API bypass anti-bot)
    use_browser = False
    if HAS_PLAYWRIGHT:
        print("\n  Initializing browser for affiliate API...")
        use_browser = _init_browser(cookie_str)
        if use_browser:
            print("  ✅ Browser ready — will fetch affiliate data via browser")
        else:
            print("  ⚠️ Browser failed — will try direct + proxy")
    else:
        print("  ⚠️ Playwright not installed — will try direct + proxy")

    # Check CF Proxy
    try:
        from shopee_proxy import is_proxy_available
        if is_proxy_available():
            print("  ✅ CF Proxy ready (fallback)")
        else:
            print("  ⚠️ CF Proxy not configured")
    except ImportError:
        print("  ⚠️ shopee_proxy.py not found")

    # Load used products — skip re-downloading products already used in videos
    used_ids = _load_used_ids()
    if used_ids:
        print(f"  ✅ Dedup: {len(used_ids)} products already used in videos — will skip")
    skipped_used = 0

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
            offers = get_products_by_keyword(headers, cookie_str, kw,
                                             target=target - collected,
                                             use_browser=use_browser)
            print(f"    → {len(offers)} offers")

            # Shorter delay for browser, longer for HTTP fallback
            if use_browser and _browser_page:
                time.sleep(random.uniform(0.5, 1.5))
            elif len(offers) == 0:
                time.sleep(random.uniform(2, 4))
            else:
                time.sleep(random.uniform(1, 2))

            for i, offer in enumerate(offers):
                if collected >= target:
                    break

                # Log first offer's structure for debugging
                if i == 0:
                    keys = list(offer.keys())[:15]
                    print(f"    [DEBUG] First offer keys: {keys}")

                # STEP 6: Extract item_id + shop_id
                item_id, shop_id = extract_ids(offer)
                if not item_id or not shop_id:
                    if i < 3:  # Log first few failures
                        print(f"    [SKIP] No IDs: item={item_id} shop={shop_id}")
                    continue

                # Skip kalau sudah ada
                nested = offer.get('batch_item_for_item_card_full', {})
                tmp_name = ''
                if isinstance(nested, dict):
                    tmp_name = nested.get('name', '')
                tmp_name = tmp_name or offer.get('product_name', str(item_id))

                pid = _gen_id(tmp_name, cat)
                if pid in used_ids:
                    skipped_used += 1
                    continue
                product_dir = os.path.join(BANK_DIR, cat, pid)
                if os.path.exists(os.path.join(product_dir, 'image.jpg')):
                    continue

                # STEP 7: Get product detail (from offer data or API)
                time.sleep(random.uniform(0.1, 0.3))
                detail = get_product_detail(item_id, shop_id, offer=offer)

                if not detail:
                    if collected == 0 and i < 5:
                        print(f"    [SKIP] No detail for {item_id}/{shop_id}")
                    continue

                # Re-generate ID with real name
                pid = _gen_id(detail['name'], cat)
                if pid in used_ids:
                    skipped_used += 1
                    continue
                product_dir = os.path.join(BANK_DIR, cat, pid)
                if os.path.exists(os.path.join(product_dir, 'image.jpg')):
                    continue

                # Download image — try ALL hashes, pick BEST quality
                os.makedirs(product_dir, exist_ok=True)
                img_path = os.path.join(product_dir, 'image.jpg')

                # Try all image hashes (prefer clean studio shots over promo graphics)
                all_hashes = detail.get('all_image_hashes', [])
                img_ok = False
                img_score = 0

                if all_hashes:
                    img_ok, img_score = _download_best_image(all_hashes, img_path)

                # Fallback: try single image_url if no hashes available
                if not img_ok:
                    img_ok = _download_image(detail['image_url'], img_path)

                if not img_ok:
                    try:
                        import shutil
                        shutil.rmtree(product_dir, ignore_errors=True)
                    except Exception:
                        pass
                    if collected == 0 and i < 5:
                        print(f"    [QC-REJECT] {detail['name'][:40]} — no quality image")
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

                # Download extra images (max 2) for slideshow — fast
                all_hashes = detail.get('all_image_hashes', [])
                if len(all_hashes) >= 2:
                    extra_saved = 0
                    for idx, h in enumerate(all_hashes[1:3], 2):  # Only 2 extras
                        if not h:
                            continue
                        extra_path = os.path.join(product_dir, f'image_{idx}.jpg')
                        if os.path.exists(extra_path):
                            extra_saved += 1
                            continue
                        img = _try_download_image(h)
                        if img:
                            img.save(extra_path, 'JPEG', quality=95)
                            extra_saved += 1
                    if extra_saved > 0:
                        print(f"      +{extra_saved} extra images")

        print(f"  → {cat}: {collected} produk baru")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  TOTAL: {total_new} produk baru")
    if skipped_used:
        print(f"  SKIPPED: {skipped_used} produk sudah dipakai video (dedup)")
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

    # Filter out products already used in videos
    used_ids = _load_used_ids()
    fresh_products = [p for p in products if p.get('produk_id', '') not in used_ids]
    skipped = len(products) - len(fresh_products)
    if skipped > 0:
        print(f"  [DEDUP] Skipped {skipped} used products from CSV export")

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    fields = ['produk_id', 'nama', 'price', 'deskripsi_singkat', 'shopee_url', 'image_url', 'category', 'source']
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for p in fresh_products:
            row = {k: p.get(k, '') for k in fields}
            if not row.get('deskripsi_singkat'):
                row['deskripsi_singkat'] = p.get('desc', '')
            w.writerow(row)
    print(f"\n✅ CSV: {len(fresh_products)} products exported ({skipped} used excluded)")


def _copy_images():
    import shutil
    dst_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'images')
    os.makedirs(dst_dir, exist_ok=True)
    # Skip products already used in videos
    used_ids = _load_used_ids()
    count = 0
    skipped = 0
    for cat in CATEGORIES:
        cat_dir = os.path.join(BANK_DIR, cat)
        if not os.path.exists(cat_dir):
            continue
        for d in os.listdir(cat_dir):
            if d in used_ids:
                skipped += 1
                continue
            src = os.path.join(cat_dir, d, 'image.jpg')
            dst = os.path.join(dst_dir, f"{d}.jpg")
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                count += 1
            # Also copy as _1 for slideshow compatibility
            dst_1 = os.path.join(dst_dir, f"{d}_1.jpg")
            if os.path.exists(src) and not os.path.exists(dst_1):
                shutil.copy2(src, dst_1)
            # Copy extra numbered images
            for i in range(2, 6):
                src_extra = os.path.join(cat_dir, d, f'image_{i}.jpg')
                dst_extra = os.path.join(dst_dir, f"{d}_{i}.jpg")
                if os.path.exists(src_extra) and not os.path.exists(dst_extra):
                    shutil.copy2(src_extra, dst_extra)
                    count += 1
    print(f"✅ Images: {count} copied ({skipped} used skipped)")


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
