"""
shopee_auto_login.py
Automatically login to affiliate.shopee.co.id and export fresh cookies.

Uses Playwright (headless browser) to:
1. Navigate DIRECTLY to affiliate.shopee.co.id (NOT shopee.co.id)
2. Complete the affiliate login flow
3. Wait for session cookies to establish
4. Navigate to Komisi XTRA page to ensure affiliate cookies are set
5. Export all cookies as JSON

Required env vars:
  SHOPEE_USERNAME  = Shopee login (email/phone)
  SHOPEE_PASSWORD  = Shopee password

Output:
  Sets SHOPEE_AFFILIATE_COOKIES via GITHUB_ENV
  Also saves to /tmp/affiliate_cookies.json as backup
"""

import os
import sys
import json
import time

AFFILIATE_URL = "https://affiliate.shopee.co.id"
KOMISI_XTRA_URL = f"{AFFILIATE_URL}/offer/brand_offer"
MAX_WAIT_SECONDS = 60  # max wait for login to complete
MIN_COOKIES_FOR_SUCCESS = 5  # at least 5 cookies = login likely worked
PRODUCTS_OUTPUT_FILE = '/tmp/affiliate_products.json'

# Cookie persistence â€” saved to /tmp and cached by GitHub Actions
# Cache is PRIVATE (not visible in public repo)
COOKIES_CACHE_FILE = '/tmp/.shopee_cookies.json'

# Keywords per category â€” same as shopee_affiliate.py
AFFILIATE_KEYWORDS = {
    'fashion': ['tas', 'sepatu', 'jam tangan', 'sneakers'],
    'gadget': ['earphone', 'powerbank', 'smartwatch', 'speaker'],
    'beauty': ['skincare', 'serum', 'sunscreen', 'makeup'],
    'home': ['rumah tangga', 'lampu', 'organizer', 'vacuum'],
    'wellness': ['olahraga', 'fitness', 'botol minum', 'vitamin'],
}


def _log_cookies(context, label=""):
    """Log cookie summary for debugging."""
    cookies = context.cookies()
    affiliate = [c for c in cookies if 'affiliate' in c.get('domain', '')]
    shopee = [c for c in cookies if 'shopee' in c.get('domain', '') and 'affiliate' not in c.get('domain', '')]
    print(f"  [{label}] Total: {len(cookies)}, Affiliate: {len(affiliate)}, Shopee: {len(shopee)}")

    # Show important cookies
    for c in cookies:
        name = c['name']
        if name.startswith('SPC_') or name in ('csrftoken', 'ds', 'sessionid'):
            print(f"    {name}: domain={c['domain']}, val={c['value'][:20]}...")
    return cookies


def _is_on_affiliate(url):
    """Check if URL hostname is affiliate.shopee.co.id (not just substring)."""
    from urllib.parse import urlparse
    return urlparse(url).hostname == 'affiliate.shopee.co.id'


def _fetch_products_via_browser(page):
    """Fetch products from affiliate API using the browser's own fetch().
    This bypasses Shopee anti-bot because it runs in a REAL browser context."""
    print("\n[AutoLogin] Step 4B: Fetching products via browser...")
    
    # â”€â”€ Ensure we're on affiliate.shopee.co.id (fetch uses relative URL) â”€â”€
    current_url = page.url
    print(f"  Current page: {current_url[:120]}")
    
    if not _is_on_affiliate(current_url):
        print(f"  âš ï¸ Not on affiliate domain (hostname={__import__('urllib.parse', fromlist=['urlparse']).urlparse(current_url).hostname})")
        print("  Navigating to affiliate.shopee.co.id...")
        try:
            page.goto('https://affiliate.shopee.co.id/offer/brand_offer', 
                      timeout=30000, wait_until='networkidle')
            time.sleep(3)
            current_url = page.url
            print(f"  After navigation: {current_url[:120]}")
            
            if not _is_on_affiliate(current_url):
                print("  âŒ Still not on affiliate domain â€” login probably failed")
                print("  âŒ Cannot fetch products without valid session")
                return {}
        except Exception as e:
            print(f"  âŒ Navigation failed: {e}")
            return {}
    
    print("  âœ… On affiliate domain â€” starting product fetch")
    all_results = {}
    
    for category, keywords in AFFILIATE_KEYWORDS.items():
        category_products = []
        # Use 2 keywords per category
        for kw in keywords[:2]:
            try:
                # Call affiliate API via browser's fetch() â€” same origin, no CORS
                result = page.evaluate("""
                    async (keyword) => {
                        try {
                            const resp = await fetch(
                                '/api/v3/offer/product/list?sort_type=1&page_offset=0&page_limit=20&keyword=' + encodeURIComponent(keyword),
                                {headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}}
                            );
                            if (!resp.ok) return {error: resp.status, text: await resp.text().catch(() => '')};
                            return await resp.json();
                        } catch(e) {
                            return {error: e.message};
                        }
                    }
                """, kw)
                
                if result and result.get('code') == 0:
                    products = result.get('data', {}).get('list', [])
                    print(f"  âœ… [{category}/{kw}] â†’ {len(products)} products")
                    # Log raw field names from first product for debugging
                    if products and not category_products:
                        first = products[0]
                        print(f"  [DEBUG] Raw API fields: {list(first.keys())}")
                        # Show a sample of key values
                        for key in ['product_name', 'item_name', 'name', 'product_image', 'image', 'long_link', 'product_link', 'offer_link']:
                            if key in first:
                                val = str(first[key])[:50]
                                print(f"    {key} = {val}")
                    # Save RAW data â€” let the reader handle field mapping
                    category_products.extend(products)
                else:
                    err = result.get('error', '?') if result else 'null'
                    print(f"  âŒ [{category}/{kw}] error={err}")
                
                time.sleep(1)  # Rate limit between requests
            except Exception as e:
                print(f"  âŒ [{category}/{kw}] Exception: {e}")
        
        all_results[category] = category_products
        print(f"  [{category}] Total: {len(category_products)} products")

    total = sum(len(v) for v in all_results.values())
    print(f"\n  â†’ Total products fetched: {total}")
    
    if total > 0:
        with open(PRODUCTS_OUTPUT_FILE, 'w') as f:
            json.dump(all_results, f, ensure_ascii=False)
        print(f"  â†’ Saved to {PRODUCTS_OUTPUT_FILE}")
    
    return all_results

def _validate_cookies_via_api(cookies_json_str):
    """Validate cookies by calling Shopee affiliate API.
    
    Tries TWO methods:
      1. Via CF proxy (if available) â€” Cloudflare PoP IP, most reliable
      2. Direct API call â€” may work from GitHub Actions IP for API endpoints
    
    Returns: cookies_json_str if valid, None if expired/invalid
    """
    if not cookies_json_str:
        return None
    
    try:
        # Parse cookies JSON (Playwright format) â†’ cookie string
        cookies = json.loads(cookies_json_str)
        cookie_parts = []
        for c in cookies:
            name = c.get('name', '')
            value = c.get('value', '')
            if name and value:
                cookie_parts.append(f"{name}={value}")
        
        if not cookie_parts:
            print("[CookieCheck] No valid cookies to test")
            return None
        
        cookies_str = '; '.join(cookie_parts)
        
        # Test URL + headers
        test_url = "https://affiliate.shopee.co.id/api/v3/offer/product/list"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://affiliate.shopee.co.id/',
            'X-Requested-With': 'XMLHttpRequest',
        }
        params = {
            'sort_type': '1',
            'page_offset': '0',
            'page_limit': '1',
            'keyword': 'tas',
        }
        from urllib.parse import urlencode
        full_url = f"{test_url}?{urlencode(params)}"
        
        # â”€â”€ Method 1: Via CF proxy â”€â”€
        data = None
        status = 0
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from shopee_proxy import proxy_get_json, is_proxy_available
            
            if is_proxy_available():
                print("[CookieCheck] Method 1: Testing via CF proxy...")
                status, data = proxy_get_json(full_url, headers=headers, cookies_str=cookies_str)
                print(f"[CookieCheck] Proxy response: HTTP {status}, data={str(data)[:200] if data else 'None'}")
        except ImportError:
            print("[CookieCheck] shopee_proxy not available")
        except Exception as e:
            print(f"[CookieCheck] Proxy error: {e}")
        
        # â”€â”€ Method 2: Direct API call (fallback) â”€â”€
        if not data or not isinstance(data, dict) or (isinstance(data, dict) and 'error' in data):
            print("[CookieCheck] Method 2: Testing via direct API call...")
            try:
                import requests
                direct_headers = dict(headers)
                direct_headers['Cookie'] = cookies_str
                resp = requests.get(full_url, headers=direct_headers, timeout=15)
                status = resp.status_code
                try:
                    data = resp.json()
                except Exception:
                    data = None
                print(f"[CookieCheck] Direct response: HTTP {status}, data={str(data)[:200] if data else 'None'}")
            except Exception as e:
                print(f"[CookieCheck] Direct API error: {e}")
        
        # â”€â”€ Evaluate response â”€â”€
        if data and isinstance(data, dict):
            code = data.get('code', -1)
            if code == 0:
                products = data.get('data', {}).get('list', [])
                print(f"[CookieCheck] âœ… Cookies VALID! API returned {len(products)} products")
                return cookies_json_str
            elif code == 30002:
                print(f"[CookieCheck] âŒ Cookies EXPIRED (code 30002: cookie incorrect)")
                return None
            elif isinstance(data.get('error', 0), int) and data.get('error', 0) > 0:
                # Shopee affiliate API returns {error: 90309999, is_login: True}
                # when cookies expired — different format than code:30002
                err = data.get('error')
                print(f"[CookieCheck] \u274c Cookies EXPIRED (error={err}, is_login={data.get('is_login')})")
                return None
            else:
                msg = data.get('msg', data.get('error', '?'))
                print(f"[CookieCheck] âš ï¸ API response: code={code}, msg={msg}")
                return None
        else:
            print(f"[CookieCheck] âš ï¸ HTTP {status}, no valid JSON response")
            return None
            
    except Exception as e:
        print(f"[CookieCheck] Error: {e}")
        return None


def auto_login():
    """Login to affiliate.shopee.co.id and return fresh cookies.
    
    Flow:
      1. PRE-CHECK: Validate existing cookies via API (proxy + direct)
         â†’ If VALID: return immediately, skip browser entirely
         â†’ If EXPIRED: try browser login (but will likely fail to CAPTCHA)
      2. BROWSER LOGIN: Only if cookies don't exist or are expired
    """
    username = os.environ.get('SHOPEE_USERNAME', '')
    password = os.environ.get('SHOPEE_PASSWORD', '')

    if not username or not password:
        print("[AutoLogin] ERROR: SHOPEE_USERNAME and SHOPEE_PASSWORD must be set")
        return None

    print(f"[AutoLogin] Logging in as: {username[:3]}***{username[-3:]}")

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  PRE-CHECK: Validate existing cookies via API call
    #  If cookies still work â†’ return immediately (skip browser!)
    #  Tries CF proxy first, then direct API call as fallback
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    existing_cookies = ''
    cookie_source = ''
    
    # Priority 1: Cache file (from previous run)
    if os.path.exists(COOKIES_CACHE_FILE):
        try:
            with open(COOKIES_CACHE_FILE, 'r') as f:
                existing_cookies = f.read().strip()
            if existing_cookies:
                cookie_source = 'cache'
        except Exception:
            pass
    
    # Priority 2: Environment/secrets
    if not existing_cookies:
        existing_cookies = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
        if existing_cookies:
            cookie_source = 'secret'
    
    if existing_cookies:
        print(f"[AutoLogin] Found cookies from {cookie_source} ({len(existing_cookies)} chars)")
        validated = _validate_cookies_via_api(existing_cookies)
        if validated:
            print("[AutoLogin] âœ… Cookies VALID via API â€” skipping browser login!")
            # Save to cache + marker
            try:
                with open(COOKIES_CACHE_FILE, 'w') as f:
                    f.write(validated)
                with open('/tmp/.cookies_session_valid', 'w') as f:
                    f.write('1')
            except Exception:
                pass
            return validated
        else:
            print("[AutoLogin] \u274c Cookies expired via API")
            print("[AutoLogin] Skipping Playwright -- GitHub Actions IP always gets CAPTCHA")
            print("[AutoLogin] --> Update SHOPEE_AFFILIATE_COOKIES secret with fresh cookies to fix")
            return None
    else:
        print("[AutoLogin] No existing cookies found")

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  BROWSER LOGIN: Only if cookies are expired or missing
    #  NOTE: From GitHub Actions, this will likely hit CAPTCHA.
    #  But we still try because sometimes it works.
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[AutoLogin] ERROR: playwright not installed")
        return None

    cookies = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='id-ID',
        )

        # Remove navigator.webdriver flag (anti-bot bypass)
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = context.new_page()

        try:
            # â”€â”€ Step 0: Inject existing cookies â”€â”€
            if existing_cookies:
                try:
                    stored = json.loads(existing_cookies)
                    pw_cookies = []
                    for c in stored:
                        cookie = {
                            'name': c.get('name', ''),
                            'value': c.get('value', ''),
                            'domain': c.get('domain', '.shopee.co.id'),
                            'path': c.get('path', '/'),
                        }
                        if cookie['name'] and cookie['value']:
                            pw_cookies.append(cookie)
                    
                    if pw_cookies:
                        context.add_cookies(pw_cookies)
                        print(f"[AutoLogin] Step 0: Injected {len(pw_cookies)} cookies")
                except (json.JSONDecodeError, TypeError) as e:
                    print(f"[AutoLogin] Step 0: Cookie parse error: {e}")

            # â”€â”€ Step 1: Navigate to affiliate site â”€â”€
            print("[AutoLogin] Step 1: Navigating to affiliate.shopee.co.id...")
            page.goto(AFFILIATE_URL, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=20000)
            time.sleep(3)

            current_url = page.url
            print(f"[AutoLogin] Current URL: {current_url}")

            # â”€â”€ Step 2: Handle login if needed â”€â”€
            needs_login = (
                'login' in current_url.lower() or
                'signin' in current_url.lower() or
                'auth' in current_url.lower() or
                'buyer/login' in current_url.lower() or
                'captcha' in current_url.lower() or
                'verify' in current_url.lower()
            )

            if not needs_login:
                login_form = page.query_selector('input[type="password"]')
                if login_form:
                    needs_login = True

            if needs_login:
                print(f"[AutoLogin] Step 2: Login required at: {current_url}")

                # Check for CAPTCHA immediately
                if 'captcha' in current_url.lower() or 'verify' in current_url.lower():
                    print("[AutoLogin] âš ï¸ CAPTCHA detected â€” cannot auto-login from this IP")
                    page.screenshot(path='/tmp/captcha_detected.png')
                    # Don't proceed with login â€” will fail
                else:
                    # Wait for SPA form
                    try:
                        page.wait_for_selector(
                            'input[type="text"], input[type="password"], input[name="loginKey"]',
                            timeout=15000
                        )
                    except Exception:
                        print("  âš ï¸ Form not rendered after 15s")
                    
                    time.sleep(2)
                    
                    # Fill username
                    for sel in ['input[name="loginKey"]', 'input[name="username"]',
                                'input[autocomplete="username"]', 'input[type="text"]',
                                'input[type="email"]', 'input[type="tel"]']:
                        try:
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                el.click()
                                time.sleep(0.5)
                                el.fill('')
                                page.keyboard.type(username, delay=50)
                                print(f"  âœ… Username filled: {sel}")
                                break
                        except Exception:
                            continue

                    time.sleep(1)

                    # Fill password
                    for sel in ['input[name="password"]', 'input[type="password"]']:
                        try:
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                el.click()
                                time.sleep(0.3)
                                page.keyboard.type(password, delay=50)
                                print(f"  âœ… Password filled: {sel}")
                                break
                        except Exception:
                            continue

                    time.sleep(1)

                    # Click login
                    for sel in ['button[type="submit"]', 'button:has-text("Log In")',
                                'button:has-text("Masuk")', '.btn-solid-primary', 'form button']:
                        try:
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                el.click()
                                print(f"  âœ… Login button clicked: {sel}")
                                break
                        except Exception:
                            continue

                    # â”€â”€ Step 3: Wait for login â”€â”€
                    print("[AutoLogin] Step 3: Waiting for login...")
                    start = time.time()
                    while time.time() - start < MAX_WAIT_SECONDS:
                        time.sleep(3)
                        current_url = page.url
                        elapsed = int(time.time() - start)
                        print(f"  [{elapsed}s] {current_url[:60]}")

                        if 'captcha' in current_url.lower() or 'verify' in current_url.lower():
                            print("  âš ï¸ CAPTCHA â€” cannot proceed automatically")
                            page.screenshot(path='/tmp/captcha.png')
                            break

                        if 'login' not in current_url.lower() and 'signin' not in current_url.lower():
                            print("  âœ… Login successful!")
                            break
            else:
                print("[AutoLogin] Step 2: Already logged in (no login page)")

            # â”€â”€ Step 4: Verify session on affiliate domain â”€â”€
            session_valid = False
            print("[AutoLogin] Step 4: Verifying session...")
            try:
                page.goto(KOMISI_XTRA_URL, timeout=30000)
                page.wait_for_load_state('networkidle', timeout=20000)
                time.sleep(5)

                current_url = page.url
                print(f"  URL: {current_url[:80]}")

                if _is_on_affiliate(current_url):
                    print("  âœ… Session valid!")
                    session_valid = True
                else:
                    print("  âŒ Not on affiliate domain â€” session invalid")
                    page.screenshot(path='/tmp/session_invalid.png')
            except Exception as e:
                print(f"  âŒ Navigation error: {e}")

            # â”€â”€ Step 5: Export cookies â”€â”€
            print("[AutoLogin] Step 5: Exporting cookies...")
            cookies = context.cookies()

            if session_valid:
                print(f"  âœ… Saving {len(cookies)} cookies to cache")
                try:
                    cookies_json = json.dumps(cookies, ensure_ascii=False)
                    with open(COOKIES_CACHE_FILE, 'w') as f:
                        f.write(cookies_json)
                    with open('/tmp/.cookies_session_valid', 'w') as f:
                        f.write('1')
                except Exception as e:
                    print(f"  âš ï¸ Save error: {e}")
            else:
                print("  âš ï¸ Session NOT valid â€” not saving (keeping old cache)")
                cookies = None

        except Exception as e:
            print(f"[AutoLogin] ERROR: {e}")
            import traceback
            traceback.print_exc()
            try:
                page.screenshot(path='/tmp/auto_login_error.png')
            except Exception:
                pass
        finally:
            browser.close()

    if not cookies:
        return None

    cookies_json = json.dumps(cookies, ensure_ascii=False)
    print(f"[AutoLogin] Cookies JSON: {len(cookies_json)} chars")

    with open('/tmp/affiliate_cookies.json', 'w') as f:
        f.write(cookies_json)
    print("[AutoLogin] Saved to /tmp/affiliate_cookies.json")

    return cookies_json


def main():
    cookies_json = auto_login()
    if cookies_json:
        github_env = os.environ.get('GITHUB_ENV', '')
        if github_env:
            with open(github_env, 'a') as f:
                f.write(f"SHOPEE_AFFILIATE_COOKIES<<EOF\n")
                f.write(cookies_json)
                f.write(f"\nEOF\n")
            print("[AutoLogin] âœ… Set SHOPEE_AFFILIATE_COOKIES in GITHUB_ENV")
        else:
            print(f"\nSHOPEE_AFFILIATE_COOKIES={cookies_json[:100]}...")

        print("[AutoLogin] âœ… Login successful!")
    else:
        print("[AutoLogin] âš ï¸ Login/cookie refresh incomplete â€” continuing anyway")
    
    # Always exit 0 â€” auto-refresh is continue-on-error
    sys.exit(0)


if __name__ == '__main__':
    main()

