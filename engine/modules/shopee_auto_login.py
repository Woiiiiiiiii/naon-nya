"""
shopee_auto_login.py
Automatically login to affiliate.shopee.co.id and export fresh cookies.

Uses Playwright (headless browser) to:
1. Navigate to affiliate.shopee.co.id
2. Login with username/password from environment
3. Wait for session to establish
4. Export all cookies as JSON
5. Save to environment / file for product_collector to use

Required env vars:
  SHOPEE_USERNAME  = Shopee login (email/phone)
  SHOPEE_PASSWORD  = Shopee password

Output:
  Prints SHOPEE_AFFILIATE_COOKIES=<json> for GitHub Actions to capture
  Also saves to /tmp/affiliate_cookies.json as backup
"""

import os
import sys
import json
import time


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
        print("[AutoLogin] ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    cookies = None

    with sync_playwright() as p:
        # Launch headless browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='id-ID',
        )

        page = context.new_page()

        try:
            # Step 1: Go to affiliate dashboard (will redirect to login)
            print("[AutoLogin] Navigating to affiliate dashboard...")
            page.goto('https://affiliate.shopee.co.id/dashboard', timeout=30000)
            time.sleep(3)

            # Check if already logged in
            current_url = page.url
            print(f"[AutoLogin] Current URL: {current_url}")

            if 'login' in current_url.lower() or 'buyer/login' in current_url.lower():
                print("[AutoLogin] Login page detected, entering credentials...")

                # Try to find and fill login form
                # Shopee login can be via email/phone
                # Wait for login form to be ready
                page.wait_for_load_state('networkidle', timeout=15000)
                time.sleep(2)

                # Try multiple selectors for username field
                username_selectors = [
                    'input[name="loginKey"]',
                    'input[name="username"]',
                    'input[type="text"]',
                    'input[placeholder*="Email"]',
                    'input[placeholder*="phone"]',
                    'input[placeholder*="Nomor"]',
                    '.shopee-input__input',
                ]

                username_filled = False
                for sel in username_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            el.fill(username)
                            username_filled = True
                            print(f"[AutoLogin] Username filled using: {sel}")
                            break
                    except Exception:
                        continue

                if not username_filled:
                    print("[AutoLogin] WARNING: Could not find username field")
                    # Take screenshot for debugging
                    page.screenshot(path='/tmp/login_page.png')
                    print("[AutoLogin] Screenshot saved to /tmp/login_page.png")

                time.sleep(1)

                # Try to find password field
                password_selectors = [
                    'input[name="password"]',
                    'input[type="password"]',
                    '.shopee-input__input[type="password"]',
                ]

                password_filled = False
                for sel in password_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            el.fill(password)
                            password_filled = True
                            print(f"[AutoLogin] Password filled using: {sel}")
                            break
                    except Exception:
                        continue

                if not password_filled:
                    print("[AutoLogin] WARNING: Could not find password field")

                time.sleep(1)

                # Click login button
                login_selectors = [
                    'button[type="submit"]',
                    'button:has-text("Log In")',
                    'button:has-text("Masuk")',
                    'button:has-text("Login")',
                    '.btn-solid-primary',
                ]

                login_clicked = False
                for sel in login_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            login_clicked = True
                            print(f"[AutoLogin] Login button clicked: {sel}")
                            break
                    except Exception:
                        continue

                if not login_clicked:
                    print("[AutoLogin] WARNING: Could not find login button")
                    page.screenshot(path='/tmp/login_page_buttons.png')

                # Wait for login to complete
                print("[AutoLogin] Waiting for login to complete...")
                time.sleep(8)

                # Check for CAPTCHA or verification
                current_url = page.url
                page_content = page.content().lower()

                if 'verify' in current_url.lower() or 'captcha' in page_content:
                    print("[AutoLogin] ⚠️  CAPTCHA/Verification detected!")
                    print("[AutoLogin] ⚠️  Auto-login cannot bypass CAPTCHA")
                    page.screenshot(path='/tmp/captcha_page.png')
                    browser.close()
                    return None

                if 'login' in current_url.lower():
                    print("[AutoLogin] ⚠️  Still on login page — credentials may be wrong")
                    page.screenshot(path='/tmp/login_failed.png')
                    browser.close()
                    return None

            # Step 2: Navigate to affiliate dashboard to ensure cookies are set
            print("[AutoLogin] Navigating to affiliate offer page...")
            page.goto('https://affiliate.shopee.co.id/offer/shopee', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            time.sleep(3)

            # Step 3: Export cookies
            cookies = context.cookies()
            print(f"[AutoLogin] Exported {len(cookies)} cookies")

            # Log domains
            domains = set(c.get('domain', '') for c in cookies)
            print(f"[AutoLogin] Domains: {', '.join(sorted(domains))}")

            # Check for auth cookies
            auth_names = [c['name'] for c in cookies if c['name'].startswith('SPC_')]
            print(f"[AutoLogin] Auth cookies: {', '.join(auth_names)}")

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

    # Convert to the JSON format expected by our code
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
        # Output for GitHub Actions to capture as env var
        # Using GITHUB_ENV file for multi-line values
        github_env = os.environ.get('GITHUB_ENV', '')
        if github_env:
            with open(github_env, 'a') as f:
                # Use delimiter for multi-line value
                f.write(f"SHOPEE_AFFILIATE_COOKIES<<EOF\n")
                f.write(cookies_json)
                f.write(f"\nEOF\n")
            print("[AutoLogin] ✅ Set SHOPEE_AFFILIATE_COOKIES in GITHUB_ENV")
        else:
            # Not in GitHub Actions — just print
            print(f"\nSHOPEE_AFFILIATE_COOKIES={cookies_json[:100]}...")

        print("[AutoLogin] ✅ Login successful!")
        sys.exit(0)
    else:
        print("[AutoLogin] ❌ Login failed!")
        sys.exit(1)


if __name__ == '__main__':
    main()
