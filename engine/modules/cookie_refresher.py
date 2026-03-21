"""
cookie_refresher.py
Auto-refresh Shopee cookies by making API calls that return Set-Cookie headers.

How it works:
1. Load existing cookies from SHOPEE_AFFILIATE_COOKIES secret
2. Make a product API call (e.g. /api/v4/pdp/hot_sales/get_item_cards)
3. Shopee responds with Set-Cookie headers containing refreshed tokens
4. Merge refreshed tokens back into cookie jar
5. Save updated cookies to GitHub secret via GH_PAT + GITHUB_ENV

Key discovery: Shopee refreshes these tokens in Set-Cookie on EVERY API call:
  - SPC_T_ID, SPC_T_IV (session token) — Max-Age=630720000 (20 years)
  - SPC_R_T_ID, SPC_R_T_IV (refresh token) — Max-Age=630720000
  - SPC_SI (session info) — Max-Age=86400 (1 day)
  - SPC_U (user ID) — Max-Age=630720000

This means cookies auto-refresh as long as we make periodic API calls!
"""

import os
import sys
import json
import requests
import subprocess


def _parse_cookies(raw):
    """Parse cookies from JSON array or cookie string format."""
    if not raw or not raw.strip():
        return []
    raw = raw.strip()

    # JSON array (Playwright export format)
    if raw.startswith('['):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    # JSON dict
    if raw.startswith('{'):
        try:
            data = json.loads(raw)
            return [{'name': k, 'value': str(v), 'domain': '.shopee.co.id'} for k, v in data.items()]
        except json.JSONDecodeError:
            pass

    # Cookie string: "name1=value1; name2=value2"
    cookies = []
    for part in raw.split(';'):
        part = part.strip()
        if '=' in part:
            name, _, value = part.partition('=')
            if name.strip() and value.strip():
                cookies.append({'name': name.strip(), 'value': value.strip(), 'domain': '.shopee.co.id'})
    return cookies


def _cookies_to_header(cookies_list):
    """Convert cookie list to HTTP Cookie header string."""
    return '; '.join(f"{c['name']}={c['value']}" for c in cookies_list if c.get('name'))


def refresh_cookies():
    """Main: refresh cookies via Shopee product API."""
    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not cookies_raw:
        print("[Refresh] SHOPEE_AFFILIATE_COOKIES not set")
        return None

    cookies_list = _parse_cookies(cookies_raw)
    if not cookies_list:
        print("[Refresh] Could not parse cookies")
        return None

    print(f"[Refresh] Loaded {len(cookies_list)} cookies")
    cookie_header = _cookies_to_header(cookies_list)

    # ── Make a product API call to trigger Set-Cookie refresh ──
    # This endpoint returns Set-Cookie with refreshed session tokens
    # Using a known popular product (any valid item_id/shop_id works)
    endpoints = [
        "https://shopee.co.id/api/v4/pdp/hot_sales/get_item_cards?item_id=22737649703&limit=8&offset=0&shop_id=977815615",
        "https://shopee.co.id/api/v4/search/search_items?by=relevancy&keyword=tas&limit=1&newest=0&order=desc&page_type=search&version=2",
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'id-ID,id;q=0.9,en;q=0.8',
        'Referer': 'https://shopee.co.id/',
        'X-Shopee-Language': 'id',
        'X-Requested-With': 'XMLHttpRequest',
        'X-Api-Source': 'pc',
        'Cookie': cookie_header,
    }

    refreshed_cookies = {}
    api_success = False

    for url in endpoints:
        print(f"[Refresh] Calling: {url.split('?')[0].split('/')[-1]}...")
        try:
            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=False)
            print(f"[Refresh] HTTP {resp.status_code}, Set-Cookie count: {len(resp.cookies)}")

            # Capture Set-Cookie headers
            for cookie in resp.cookies:
                refreshed_cookies[cookie.name] = {
                    'name': cookie.name,
                    'value': cookie.value,
                    'domain': cookie.domain or '.shopee.co.id',
                    'path': cookie.path or '/',
                }
                print(f"  Set-Cookie: {cookie.name} (Max-Age={cookie.get_nonstandard_attr('Max-Age', '?')})")

            if resp.status_code == 200:
                api_success = True
                try:
                    data = resp.json()
                    # Check if we got a valid response (not an error)
                    if isinstance(data, dict):
                        error = data.get('error', 0)
                        code = data.get('code', data.get('error_msg', ''))
                        if error and isinstance(error, int) and error > 0:
                            print(f"[Refresh] API error: {error}")
                        else:
                            print(f"[Refresh] API response OK")
                except Exception:
                    pass

            if refreshed_cookies:
                break  # Got refreshed cookies, no need to try more endpoints

        except Exception as e:
            print(f"[Refresh] Error: {e}")

    if not refreshed_cookies:
        print("[Refresh] No Set-Cookie received — cookies may be fully expired")
        print("[Refresh] Manual update of SHOPEE_AFFILIATE_COOKIES needed")
        return None

    # ── Merge refreshed cookies into existing ones ──
    print(f"\n[Refresh] Merging {len(refreshed_cookies)} refreshed cookies...")
    existing_by_name = {c['name']: i for i, c in enumerate(cookies_list)}

    updated_count = 0
    for name, new_cookie in refreshed_cookies.items():
        if name in existing_by_name:
            idx = existing_by_name[name]
            old_val = cookies_list[idx]['value']
            new_val = new_cookie['value']
            if old_val != new_val:
                cookies_list[idx]['value'] = new_val
                print(f"  Updated: {name}")
                updated_count += 1
            else:
                print(f"  Unchanged: {name}")
        else:
            cookies_list.append(new_cookie)
            print(f"  Added: {name}")
            updated_count += 1

    if updated_count == 0:
        print("[Refresh] No cookies changed — already fresh")
    else:
        print(f"[Refresh] {updated_count} cookies refreshed!")

    # ── Save refreshed cookies ──
    refreshed_json = json.dumps(cookies_list, ensure_ascii=False)
    print(f"[Refresh] Total: {len(cookies_list)} cookies, {len(refreshed_json)} chars")

    # Save to cache file
    try:
        with open('/tmp/.shopee_cookies.json', 'w') as f:
            f.write(refreshed_json)
        with open('/tmp/.cookies_session_valid', 'w') as f:
            f.write('1')
        print("[Refresh] Saved to cache")
    except Exception as e:
        print(f"[Refresh] Cache error: {e}")

    # Update GitHub secret
    gh_token = os.environ.get('GH_TOKEN', '')
    if gh_token:
        try:
            result = subprocess.run(
                ['gh', 'secret', 'set', 'SHOPEE_AFFILIATE_COOKIES'],
                input=refreshed_json, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                print("[Refresh] SHOPEE_AFFILIATE_COOKIES secret UPDATED!")
            else:
                print(f"[Refresh] Secret update failed: {result.stderr[:200]}")
        except Exception as e:
            print(f"[Refresh] gh CLI error: {e}")

    # Set GITHUB_ENV for downstream steps
    github_env = os.environ.get('GITHUB_ENV', '')
    if github_env:
        try:
            with open(github_env, 'a') as f:
                f.write(f"SHOPEE_AFFILIATE_COOKIES<<EOF\n{refreshed_json}\nEOF\n")
            print("[Refresh] Set GITHUB_ENV")
        except Exception as e:
            print(f"[Refresh] ENV error: {e}")

    return refreshed_json


if __name__ == '__main__':
    result = refresh_cookies()
    if result:
        print("\n=== REFRESH SUCCESS ===")
    else:
        print("\n=== REFRESH FAILED — manual update needed ===")
    sys.exit(0)
