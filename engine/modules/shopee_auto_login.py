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

# Keywords per category — same as shopee_affiliate.py
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


def _fetch_products_via_browser(page):
    """Fetch products from affiliate API using the browser's own fetch().
    This bypasses Shopee anti-bot because it runs in a REAL browser context."""
    print("\n[AutoLogin] Step 4B: Fetching products via browser...")
    all_results = {}
    
    for category, keywords in AFFILIATE_KEYWORDS.items():
        category_products = []
        # Use 2 keywords per category
        for kw in keywords[:2]:
            try:
                # Call affiliate API via browser's fetch() — same origin, no CORS
                result = page.evaluate("""
                    async (keyword) => {
                        try {
                            const resp = await fetch(
                                '/api/v3/offer/product/list?sort_type=1&page_offset=0&page_limit=10&keyword=' + encodeURIComponent(keyword),
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
                    print(f"  ✅ [{category}/{kw}] → {len(products)} products")
                    for p in products:
                        category_products.append({
                            'product_name': p.get('product_name', p.get('item_name', '')),
                            'product_image': p.get('product_image', p.get('image', '')),
                            'long_link': p.get('long_link', p.get('product_link', '')),
                            'commission_rate': p.get('commission_rate', '0%'),
                            'price': p.get('price', p.get('product_price', 0)),
                            'shop_name': p.get('shop_name', ''),
                        })
                else:
                    err = result.get('error', '?') if result else 'null'
                    print(f"  ❌ [{category}/{kw}] error={err}")
                
                time.sleep(1)  # Rate limit between requests
            except Exception as e:
                print(f"  ❌ [{category}/{kw}] Exception: {e}")
        
        all_results[category] = category_products
        print(f"  [{category}] Total: {len(category_products)} products")
    
    total = sum(len(v) for v in all_results.values())
    print(f"\n  → Total products fetched: {total}")
    
    if total > 0:
        with open(PRODUCTS_OUTPUT_FILE, 'w') as f:
            json.dump(all_results, f, ensure_ascii=False)
        print(f"  → Saved to {PRODUCTS_OUTPUT_FILE}")
    
    return all_results


def auto_login():
    """Login to affiliate.shopee.co.id and return fresh cookies."""
    username = os.environ.get('SHOPEE_USERNAME', '')
    password = os.environ.get('SHOPEE_PASSWORD', '')

    if not username or not password:
        print("[AutoLogin] ERROR: SHOPEE_USERNAME and SHOPEE_PASSWORD must be set")
        return None

    print(f"[AutoLogin] Logging in as: {username[:3]}***{username[-3:]}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[AutoLogin] ERROR: playwright not installed")
        return None

    cookies = None

    with sync_playwright() as p:
        # Use stealth-like settings to avoid bot detection
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
            # ═══════════════════════════════════════════════════════
            #  STEP 1: Go DIRECTLY to affiliate.shopee.co.id
            #  This will redirect to the affiliate login page
            #  (NOT shopee.co.id/buyer/login)
            # ═══════════════════════════════════════════════════════
            print("[AutoLogin] Step 1: Navigating to affiliate.shopee.co.id...")
            page.goto(AFFILIATE_URL, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=20000)
            time.sleep(3)

            current_url = page.url
            print(f"[AutoLogin] Current URL: {current_url}")
            page.screenshot(path='/tmp/step1_page.png')

            # ═══════════════════════════════════════════════════════
            #  STEP 2: Handle login
            #  affiliate.shopee.co.id may redirect to:
            #  a) Its own login form
            #  b) Shopee SSO login
            #  c) Already logged in (if cookies exist)
            # ═══════════════════════════════════════════════════════
            needs_login = (
                'login' in current_url.lower() or
                'signin' in current_url.lower() or
                'auth' in current_url.lower() or
                'buyer/login' in current_url.lower()
            )

            # Also check if page has login form
            if not needs_login:
                login_form = page.query_selector('input[type="password"]')
                if login_form:
                    needs_login = True
                    print("[AutoLogin] Found password field — login required")

            if needs_login:
                print(f"[AutoLogin] Step 2: Login required at: {current_url}")

                # ── Fill username ──
                username_selectors = [
                    'input[name="loginKey"]',
                    'input[name="username"]',
                    'input[name="email"]',
                    'input[autocomplete="username"]',
                    'input[type="text"]:not([type="hidden"])',
                    'input[type="email"]',
                    'input[placeholder*="Email"]',
                    'input[placeholder*="email"]',
                    'input[placeholder*="phone"]',
                    'input[placeholder*="Nomor"]',
                    'input[placeholder*="Login"]',
                    'input[placeholder*="Username"]',
                    '.shopee-input__input',
                    '#username',
                    '#email',
                ]

                username_filled = False
                for sel in username_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            time.sleep(0.5)
                            # Clear existing value first
                            el.fill('')
                            time.sleep(0.2)
                            # Type character by character (more human-like)
                            page.keyboard.type(username, delay=50)
                            username_filled = True
                            print(f"  ✅ Username filled via: {sel}")
                            break
                    except Exception:
                        continue

                if not username_filled:
                    print("  ⚠️ Could not find username field!")
                    # Try finding ANY visible text input
                    all_inputs = page.query_selector_all('input:visible')
                    print(f"  Visible inputs: {len(all_inputs)}")
                    for i, inp in enumerate(all_inputs):
                        inp_type = inp.get_attribute('type') or 'text'
                        inp_name = inp.get_attribute('name') or '?'
                        inp_ph = inp.get_attribute('placeholder') or '?'
                        print(f"    [{i}] type={inp_type}, name={inp_name}, placeholder={inp_ph}")
                    page.screenshot(path='/tmp/login_page.png')

                time.sleep(1)

                # ── Fill password ──
                password_selectors = [
                    'input[name="password"]',
                    'input[type="password"]',
                    'input[autocomplete="current-password"]',
                    '#password',
                ]

                password_filled = False
                for sel in password_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            time.sleep(0.3)
                            page.keyboard.type(password, delay=50)
                            password_filled = True
                            print(f"  ✅ Password filled via: {sel}")
                            break
                    except Exception:
                        continue

                if not password_filled:
                    print("  ⚠️ Could not find password field!")
                    page.screenshot(path='/tmp/login_nopass.png')

                time.sleep(1)

                # ── Click login button ──
                login_selectors = [
                    'button[type="submit"]',
                    'button:has-text("Log In")',
                    'button:has-text("Masuk")',
                    'button:has-text("LOGIN")',
                    'button:has-text("Sign In")',
                    '.btn-solid-primary',
                    'button.shopee-button--primary',
                    'form button',
                ]

                login_clicked = False
                for sel in login_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            login_clicked = True
                            print(f"  ✅ Login button clicked: {sel}")
                            break
                    except Exception:
                        continue

                if not login_clicked:
                    # Try pressing Enter instead
                    print("  ⚠️ No login button found — pressing Enter")
                    page.keyboard.press('Enter')

                # ═══════════════════════════════════════════════════
                #  STEP 3: Wait for login to complete
                # ═══════════════════════════════════════════════════
                print("[AutoLogin] Step 3: Waiting for login to complete...")
                start = time.time()
                login_success = False

                while time.time() - start < MAX_WAIT_SECONDS:
                    time.sleep(3)
                    current_url = page.url
                    elapsed = int(time.time() - start)
                    all_cookies = context.cookies()

                    print(f"  [{elapsed}s] URL: {current_url[:60]}..., Cookies: {len(all_cookies)}")

                    # Check for CAPTCHA/verification
                    if 'verify' in current_url.lower() or 'captcha' in current_url.lower():
                        print("  ⚠️ CAPTCHA/verification detected!")
                        page.screenshot(path='/tmp/captcha.png')
                        # Don't exit immediately — sometimes captcha passes automatically
                        continue

                    # Check if we left the login page
                    not_on_login = (
                        'login' not in current_url.lower() and
                        'signin' not in current_url.lower() and
                        'auth' not in current_url.lower()
                    )

                    if not_on_login:
                        print(f"  ✅ Redirected away from login! URL: {current_url[:80]}")
                        login_success = True
                        break

                    # Even if on login-like URL, check if we have enough cookies
                    if len(all_cookies) >= MIN_COOKIES_FOR_SUCCESS:
                        # Check if affiliate cookies specifically are present
                        aff_cookies = [c for c in all_cookies if 'affiliate' in c.get('domain', '')]
                        if aff_cookies:
                            print(f"  ✅ Got {len(aff_cookies)} affiliate cookies — login likely succeeded")
                            login_success = True
                            break

                if not login_success:
                    print(f"  ⚠️ Login may not have completed (waited {MAX_WAIT_SECONDS}s)")
                    page.screenshot(path='/tmp/login_timeout.png')
                    _log_cookies(context, "Timeout")
                    # Continue anyway — maybe partial cookies work

            else:
                print("[AutoLogin] Step 2: Already logged in (no login page detected)")

            # ═══════════════════════════════════════════════════════
            #  STEP 4: Navigate to Komisi XTRA page
            #  This ensures all affiliate-specific cookies are set
            # ═══════════════════════════════════════════════════════
            print("[AutoLogin] Step 4: Navigating to Komisi XTRA...")
            try:
                page.goto(KOMISI_XTRA_URL, timeout=30000)
                page.wait_for_load_state('networkidle', timeout=20000)
                time.sleep(5)

                current_url = page.url
                print(f"  URL after nav: {current_url[:80]}")

                # If redirected back to login, cookies didn't work
                if 'login' in current_url.lower():
                    print("  ⚠️ Redirected to login — session not established")
                    page.screenshot(path='/tmp/komisi_xtra_redirect.png')
                else:
                    print("  ✅ Komisi XTRA page loaded — session valid!")
            except Exception as e:
                print(f"  Komisi XTRA navigation: {e}")

            # ═══════════════════════════════════════════════════════
            #  STEP 4B: Fetch products via browser API
            #  Uses page.evaluate(fetch()) — runs in real browser
            #  context so Shopee's anti-bot doesn't block it
            # ═══════════════════════════════════════════════════════
            try:
                _fetch_products_via_browser(page)
            except Exception as e:
                print(f"[AutoLogin] Product fetch error (non-fatal): {e}")

            # ═══════════════════════════════════════════════════════
            #  STEP 5: Export ALL cookies
            # ═══════════════════════════════════════════════════════
            print("[AutoLogin] Step 5: Exporting cookies...")
            cookies = context.cookies()
            _log_cookies(context, "Final export")

            if len(cookies) < MIN_COOKIES_FOR_SUCCESS:
                print(f"  ❌ Only {len(cookies)} cookies — login likely failed")
                page.screenshot(path='/tmp/login_failed_final.png')
                cookies = None
            else:
                print(f"  ✅ Exporting {len(cookies)} cookies total")

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

    # Convert to JSON
    cookies_json = json.dumps(cookies, ensure_ascii=False)
    print(f"[AutoLogin] Cookies JSON: {len(cookies_json)} chars")

    # Save to file
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
            print("[AutoLogin] ✅ Set SHOPEE_AFFILIATE_COOKIES in GITHUB_ENV")
        else:
            print(f"\nSHOPEE_AFFILIATE_COOKIES={cookies_json[:100]}...")

        print("[AutoLogin] ✅ Login successful!")
        sys.exit(0)
    else:
        print("[AutoLogin] ❌ Login failed!")
        sys.exit(1)


if __name__ == '__main__':
    main()
