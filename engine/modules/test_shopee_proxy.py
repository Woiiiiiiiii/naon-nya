"""
test_shopee_proxy.py
Standalone diagnostic: test CF Worker Shopee proxy end-to-end.
Run on CI to see EXACTLY what happens when calling Shopee API through the proxy.

Usage:
  python engine/modules/test_shopee_proxy.py
"""
import os
import sys
import json
import requests
import time

sys.path.insert(0, os.path.dirname(__file__))

def test_proxy():
    print("=" * 60)
    print("  SHOPEE PROXY DIAGNOSTIC TEST")
    print("=" * 60)

    # 1. Check environment variables
    proxy_url = os.environ.get('CF_PROXY_URL', '').rstrip('/')
    proxy_key = os.environ.get('CF_PROXY_KEY', os.environ.get('CF_PROXY_KEY_API', ''))
    cookies_raw = os.environ.get('SHOPEE_COOKIES', '')

    print(f"\n[1] ENVIRONMENT VARIABLES")
    print(f"  CF_PROXY_URL:   {'SET -> ' + proxy_url[:50] + '...' if proxy_url else 'NOT SET !!!'}")
    print(f"  CF_PROXY_KEY:   {'SET -> ' + str(len(proxy_key)) + ' chars' if proxy_key else 'NOT SET !!!'}")
    print(f"  SHOPEE_COOKIES: {'SET -> ' + str(len(cookies_raw)) + ' chars' if cookies_raw else 'NOT SET !!!'}")

    if not proxy_url:
        print("\n  FATAL: CF_PROXY_URL is not set. Cannot proceed.")
        print("  Fix: Add CF_PROXY_URL to GitHub secrets")
        return False
    if not proxy_key:
        print("\n  FATAL: CF_PROXY_KEY is not set. Cannot proceed.")
        print("  Fix: Add CF_PROXY_KEY_API to GitHub secrets")
        return False

    # 2. Test CF Worker health (just ping the URL)
    print(f"\n[2] CF WORKER HEALTH CHECK")
    try:
        resp = requests.get(proxy_url, timeout=10)
        print(f"  GET {proxy_url}")
        print(f"  Status: {resp.status_code}")
        print(f"  Body: {resp.text[:200]}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 3. Test proxy with a simple Shopee CDN image (should always work)
    print(f"\n[3] TEST: Shopee CDN image via proxy")
    test_img_url = "https://down-id.img.susercontent.com/file/id-11134207-7rasg-m2uunbfkjzyw15"
    payload = {
        'url': test_img_url,
        'method': 'GET',
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 14) Chrome/121.0.0.0 Mobile',
            'Referer': 'https://shopee.co.id/',
        },
        'cookies': '',
    }
    try:
        resp = requests.post(
            f"{proxy_url}/proxy",
            json=payload,
            headers={'X-Proxy-Key': proxy_key, 'Content-Type': 'application/json'},
            timeout=20,
        )
        print(f"  Status: {resp.status_code}")
        print(f"  Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
        print(f"  Content-Length: {len(resp.content)} bytes")
        print(f"  X-Proxy-Status: {resp.headers.get('X-Proxy-Status', 'N/A')}")
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(f"  RESULT: OK - image downloaded ({len(resp.content)//1024}KB)")
        elif resp.status_code == 401:
            print(f"  RESULT: FAIL - 401 Unauthorized. PROXY_SECRET mismatch!")
            print(f"  Fix: CF Worker PROXY_SECRET must match CF_PROXY_KEY_API in GitHub")
        else:
            print(f"  RESULT: FAIL - unexpected response")
            print(f"  Body: {resp.text[:200]}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 4. Test Shopee Search API via proxy (the critical test)
    print(f"\n[4] TEST: Shopee Search API via proxy (PUBLIC, no cookies)")
    search_url = "https://shopee.co.id/api/v4/search/search_items?by=relevancy&keyword=tas+wanita&limit=3&newest=0&order=desc&page_type=search&scenario=PAGE_GLOBAL_SEARCH&version=2"
    payload = {
        'url': search_url,
        'method': 'GET',
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/121.0.6167.101 Mobile Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'id-ID,id;q=0.9,en;q=0.8',
            'Referer': 'https://shopee.co.id/search?keyword=tas+wanita',
            'X-Shopee-Language': 'id',
            'X-Requested-With': 'XMLHttpRequest',
        },
        'cookies': '',
    }
    try:
        time.sleep(1)
        resp = requests.post(
            f"{proxy_url}/proxy",
            json=payload,
            headers={'X-Proxy-Key': proxy_key, 'Content-Type': 'application/json'},
            timeout=20,
        )
        print(f"  Status: {resp.status_code}")
        print(f"  Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
        print(f"  X-Proxy-Status: {resp.headers.get('X-Proxy-Status', 'N/A')}")
        print(f"  Body length: {len(resp.text)} chars")

        if resp.status_code == 401:
            print(f"  RESULT: FAIL - 401 Unauthorized. PROXY_SECRET mismatch!")
        elif resp.status_code == 403:
            print(f"  RESULT: FAIL - Shopee returned 403 even through CF Worker")
            print(f"  This means CF Worker IP is also blocked by Shopee")
        elif resp.status_code == 200:
            try:
                data = resp.json()
                items = data.get('items', [])
                error = data.get('error', data.get('error_msg', ''))
                nomore = data.get('nomore', None)
                print(f"  JSON keys: {list(data.keys())[:10]}")
                print(f"  items count: {len(items)}")
                print(f"  error: {error}")
                print(f"  nomore: {nomore}")
                if items:
                    print(f"  RESULT: SUCCESS! Got {len(items)} products")
                    first = items[0].get('item_basic', items[0])
                    print(f"  First product: {first.get('name', '?')[:50]}")
                    print(f"  Price: {first.get('price', '?')}")
                    print(f"  Image hash: {first.get('image', '?')}")
                    print(f"  Shop ID: {first.get('shopid', '?')}")
                    print(f"  Item ID: {first.get('itemid', '?')}")
                else:
                    print(f"  RESULT: FAIL - Shopee returned 200 but 0 items")
                    print(f"  Full response (first 500 chars): {resp.text[:500]}")
            except json.JSONDecodeError:
                print(f"  RESULT: FAIL - response is not JSON")
                print(f"  Body: {resp.text[:500]}")
        else:
            print(f"  RESULT: FAIL - unexpected status {resp.status_code}")
            print(f"  Body: {resp.text[:300]}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 5. Test with cookies if available
    if cookies_raw:
        print(f"\n[5] TEST: Shopee Search API via proxy (WITH COOKIES)")
        try:
            cookies = json.loads(cookies_raw)
            if isinstance(cookies, list):
                cookies_str = '; '.join([f"{c.get('name','')}={c.get('value','')}" for c in cookies if c.get('name')])
            elif isinstance(cookies, dict):
                cookies_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
            else:
                cookies_str = ''
            print(f"  Cookies parsed: {len(cookies_str)} chars")

            payload['cookies'] = cookies_str
            time.sleep(1)
            resp = requests.post(
                f"{proxy_url}/proxy",
                json=payload,
                headers={'X-Proxy-Key': proxy_key, 'Content-Type': 'application/json'},
                timeout=20,
            )
            print(f"  Status: {resp.status_code}")
            print(f"  X-Proxy-Status: {resp.headers.get('X-Proxy-Status', 'N/A')}")
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    items = data.get('items', [])
                    print(f"  items count: {len(items)}")
                    if items:
                        print(f"  RESULT: SUCCESS with cookies!")
                    else:
                        print(f"  RESULT: FAIL - cookies helped but 0 items")
                        print(f"  Response: {resp.text[:300]}")
                except:
                    print(f"  Non-JSON response: {resp.text[:200]}")
            else:
                print(f"  Status {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"  Cookie parse error: {e}")
    else:
        print(f"\n[5] SKIP: No SHOPEE_COOKIES set")

    print(f"\n{'=' * 60}")
    print(f"  DIAGNOSTIC COMPLETE")
    print(f"{'=' * 60}")
    return True


if __name__ == "__main__":
    test_proxy()
