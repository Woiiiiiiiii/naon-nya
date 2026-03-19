"""
shopee_auto_login.py
Automatically login to affiliate.shopee.co.id and export fresh cookies.

Uses Playwright (headless browser) to:
1. Navigate to affiliate.shopee.co.id
2. Login with username/password from environment
3. Wait for session to FULLY establish (SPC_EC, SPC_ST, SPC_U)
4. Navigate to Komisi XTRA page to ensure all cookies set
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

# Cookies to LOOK FOR (but NOT required — affiliate works without them)
# SPC_EC/SPC_ST/SPC_U are set by shopee.co.id login but not always needed
DESIRED_COOKIES = ['SPC_EC', 'SPC_ST', 'SPC_U']
MAX_WAIT_FOR_COOKIES = 30  # seconds
MIN_COOKIES_FOR_SUCCESS = 5  # at least 5 cookies = login likely worked


def _has_desired_cookies(context):
    """Check if browser context has desired SPC cookies (NOT required)."""
    cookies = context.cookies()
    names = {c['name'] for c in cookies}
    missing = [c for c in DESIRED_COOKIES if c not in names]
    return len(missing) == 0, missing, len(cookies)


def _log_cookies(context, label=""):
    """Log all SPC cookies for debugging."""
    cookies = context.cookies()
    spc = [c for c in cookies if c['name'].startswith('SPC_')]
    print(f"  [{label}] Total cookies: {len(cookies)}, SPC cookies: {len(spc)}")
    for c in spc:
        print(f"    {c['name']}: domain={c['domain']}, val={c['value'][:15]}...")
    return cookies


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
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='id-ID',
        )

        page = context.new_page()

        try:
            # ═══════════════════════════════════════════════════════
            #  STEP 1: Go to Shopee main login page first
            #  SPC_EC/SPC_ST are set on .shopee.co.id domain
            #  which requires visiting the main Shopee site
            # ═══════════════════════════════════════════════════════
            print("[AutoLogin] Step 1: Navigating to Shopee login...")
            page.goto('https://shopee.co.id/buyer/login', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            time.sleep(3)

            current_url = page.url
            print(f"[AutoLogin] Current URL: {current_url}")

            # ═══════════════════════════════════════════════════════
            #  STEP 2: Fill login form
            # ═══════════════════════════════════════════════════════
            if 'login' in current_url.lower():
                print("[AutoLogin] Step 2: Filling login form...")

                # Username field
                username_selectors = [
                    'input[name="loginKey"]',
                    'input[name="username"]',
                    'input[autocomplete="username"]',
                    'input[type="text"]:not([type="hidden"])',
                    'input[placeholder*="Email"]',
                    'input[placeholder*="phone"]',
                    'input[placeholder*="Nomor"]',
                    'input[placeholder*="No."]',
                    '.shopee-input__input',
                ]

                username_filled = False
                for sel in username_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            time.sleep(0.3)
                            el.fill(username)
                            username_filled = True
                            print(f"  Username filled: {sel}")
                            break
                    except Exception:
                        continue

                if not username_filled:
                    print("  ⚠️ Could not find username field!")
                    page.screenshot(path='/tmp/login_page.png')

                time.sleep(1)

                # Password field
                password_selectors = [
                    'input[name="password"]',
                    'input[type="password"]',
                    'input[autocomplete="current-password"]',
                ]

                password_filled = False
                for sel in password_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            time.sleep(0.3)
                            el.fill(password)
                            password_filled = True
                            print(f"  Password filled: {sel}")
                            break
                    except Exception:
                        continue

                if not password_filled:
                    print("  ⚠️ Could not find password field!")

                time.sleep(1)

                # Click login button
                login_selectors = [
                    'button[type="submit"]',
                    'button:has-text("Log In")',
                    'button:has-text("Masuk")',
                    'button:has-text("LOGIN")',
                    '.btn-solid-primary',
                    'button.wyhvVD',
                ]

                login_clicked = False
                for sel in login_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            login_clicked = True
                            print(f"  Login button clicked: {sel}")
                            break
                    except Exception:
                        continue

                if not login_clicked:
                    print("  ⚠️ Could not find login button!")
                    page.screenshot(path='/tmp/login_buttons.png')

                # ═══════════════════════════════════════════════════
                #  STEP 3: Wait for SPC cookies to appear
                #  Shopee sets SPC_EC/SPC_ST AFTER full auth completion
                #  which may involve background API calls
                # ═══════════════════════════════════════════════════
                print("[AutoLogin] Step 3: Waiting for session cookies...")

                # Wait and poll for cookies (SPC desired but not required)
                start = time.time()
                while time.time() - start < MAX_WAIT_FOR_COOKIES:
                    time.sleep(2)
                    has_all, missing, total = _has_desired_cookies(context)
                    elapsed = int(time.time() - start)
                    print(f"  [{elapsed}s] Total cookies: {total}, SPC missing: {', '.join(missing) if missing else 'NONE ✅'}")

                    if has_all:
                        print(f"  ✅ All SPC cookies found after {elapsed}s!")
                        break

                    # Check if stuck on captcha
                    current_url = page.url
                    if 'verify' in current_url.lower() or 'captcha' in current_url.lower():
                        print("  ⚠️ CAPTCHA/verification detected!")
                        page.screenshot(path='/tmp/captcha.png')
                        browser.close()
                        return None

                    # If we have enough cookies, don't wait for SPC
                    if total >= MIN_COOKIES_FOR_SUCCESS:
                        print(f"  ✅ Have {total} cookies (SPC optional) — continuing")
                        break
                else:
                    # Timeout — log what we DO have
                    print(f"  ⚠️ Timeout after {MAX_WAIT_FOR_COOKIES}s")
                    _log_cookies(context, "Timeout")

                # Check if still on login page with NO cookies
                current_url = page.url
                if 'login' in current_url.lower():
                    print(f"  ⚠️ Still on login page: {current_url}")
                    page.screenshot(path='/tmp/login_failed.png')
                    all_cookies = context.cookies()
                    if len(all_cookies) < MIN_COOKIES_FOR_SUCCESS:
                        print(f"  ❌ Login failed — only {len(all_cookies)} cookies (need {MIN_COOKIES_FOR_SUCCESS}+)")
                        browser.close()
                        return None
                    else:
                        print(f"  ⚠️ On login page but have {len(all_cookies)} cookies — proceeding")

            # ═══════════════════════════════════════════════════════
            #  STEP 4: Navigate to main Shopee to trigger cookie set
            #  Some SPC cookies only get set when you visit shopee.co.id
            # ═══════════════════════════════════════════════════════
            print("[AutoLogin] Step 4: Visiting shopee.co.id for full cookies...")
            try:
                page.goto('https://shopee.co.id/', timeout=15000)
                page.wait_for_load_state('domcontentloaded', timeout=10000)
                time.sleep(3)
            except Exception as e:
                print(f"  shopee.co.id navigation: {e}")

            _log_cookies(context, "After shopee.co.id")

            # ═══════════════════════════════════════════════════════
            #  STEP 5: Navigate to affiliate dashboard
            #  This ensures affiliate-specific cookies are also set
            # ═══════════════════════════════════════════════════════
            print("[AutoLogin] Step 5: Navigating to affiliate Komisi XTRA...")
            try:
                page.goto('https://affiliate.shopee.co.id/offer/brand_offer',
                          timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                time.sleep(5)
            except Exception as e:
                print(f"  Affiliate nav: {e}")

            # ═══════════════════════════════════════════════════════
            #  STEP 6: Export ALL cookies from ALL domains
            # ═══════════════════════════════════════════════════════
            print("[AutoLogin] Step 6: Exporting cookies...")
            cookies = context.cookies()
            _log_cookies(context, "Final export")

            # Final check — SPC_EC/SPC_ST are nice to have, not required
            has_all, missing, total = _has_desired_cookies(context)
            if not has_all:
                print(f"  ℹ️ SPC cookies missing: {', '.join(missing)} (OK — affiliate works without them)")
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
