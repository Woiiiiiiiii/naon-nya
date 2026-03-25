"""
prefetch_browser.py
Pre-fetch products via Playwright browser to bypass Shopee anti-bot.

Called by GitHub Actions workflow BEFORE the main collector.
Saves results to /tmp/affiliate_products.json.

The browser's fetch() runs in real browser context with all cookies,
JavaScript anti-bot tokens generated naturally — NO manual headers needed.
"""

import os
import sys
import json
import time


def prefetch():
    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not cookies_raw:
        print('No cookies — skipping pre-fetch')
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Playwright not installed — skipping')
        return

    print('=== Pre-fetching products via browser ===')
    cookies = json.loads(cookies_raw)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='id-ID'
        )
        ctx.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined});')

        # Inject cookies
        pw_cookies = []
        for c in cookies:
            cookie = {
                'name': c.get('name', ''),
                'value': c.get('value', ''),
                'domain': c.get('domain', '.shopee.co.id'),
                'path': c.get('path', '/'),
            }
            if cookie['name'] and cookie['value']:
                pw_cookies.append(cookie)
        ctx.add_cookies(pw_cookies)
        print(f'Injected {len(pw_cookies)} cookies')

        page = ctx.new_page()
        try:
            page.goto('https://affiliate.shopee.co.id/offer/brand_offer',
                       timeout=30000, wait_until='networkidle')
        except Exception as e:
            print(f'Navigation error: {e}')
            browser.close()
            return

        time.sleep(3)
        print(f'Page: {page.url}')

        if 'affiliate.shopee.co.id' not in page.url:
            print('Not on affiliate domain — cookies may be expired')
            browser.close()
            return

        # Fetch products per category via browser fetch()
        # Browser handles ALL anti-bot tokens automatically
        categories = {
            'fashion': ['tas', 'sepatu', 'jam tangan'],
            'gadget': ['earphone', 'powerbank', 'smartwatch'],
            'beauty': ['skincare', 'serum', 'sunscreen'],
            'home': ['rumah tangga', 'lampu', 'organizer'],
            'wellness': ['olahraga', 'vitamin', 'botol minum'],
        }

        all_results = {}
        for cat, keywords in categories.items():
            cat_products = []
            for kw in keywords:
                try:
                    # Use page.evaluate to call fetch() in browser context
                    # This is same-origin, so NO CORS and anti-bot tokens
                    # are automatically included by the browser
                    result = page.evaluate("""
                        async (keyword) => {
                            try {
                                const resp = await fetch(
                                    "/api/v3/offer/product/list?list_type=5&sort_type=5&page_offset=0&page_limit=20&client_type=1&keyword=" + encodeURIComponent(keyword),
                                    {headers: {"Accept": "application/json"}}
                                );
                                if (!resp.ok) return {error: resp.status};
                                return await resp.json();
                            } catch(e) { return {error: e.message}; }
                        }
                    """, kw)

                    if result and result.get('code') == 0:
                        items = result.get('data', {}).get('list', [])
                        cat_products.extend(items)
                        print(f'  {cat}/{kw}: {len(items)} products')
                    else:
                        err = result.get('error', '?') if result else 'null'
                        print(f'  {cat}/{kw}: error={err}')

                    time.sleep(1)
                except Exception as e:
                    print(f'  {cat}/{kw}: {e}')

            all_results[cat] = cat_products
            print(f'  [{cat}] total: {len(cat_products)}')

        browser.close()

        total = sum(len(v) for v in all_results.values())
        print(f'\nTotal pre-fetched: {total}')

        if total > 0:
            with open('/tmp/affiliate_products.json', 'w') as f:
                json.dump(all_results, f, ensure_ascii=False)
            print('Saved to /tmp/affiliate_products.json')
        else:
            print('No products fetched — check cookies')


if __name__ == '__main__':
    prefetch()
