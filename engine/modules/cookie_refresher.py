"""
cookie_refresher.py
Refresh Shopee affiliate cookies via API — NO browser, NO CAPTCHA.

How it works:
1. Take existing cookies from SHOPEE_AFFILIATE_COOKIES secret
2. Make API call to affiliate.shopee.co.id (via CF proxy or direct)
3. Capture Set-Cookie headers from response → new refreshed tokens
4. Merge refreshed tokens with existing cookies
5. Save back to GitHub secret via GH_PAT

This runs as a cron every 2 hours to keep cookies alive.
"""

import os
import sys
import json
import requests
import subprocess


def _parse_cookies_json(raw):
    """Parse cookies from JSON (Playwright format) or cookie string format."""
    if not raw or not raw.strip():
        return []
    
    raw = raw.strip()
    
    # Try JSON array first (Playwright export)
    if raw.startswith('['):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    
    # Try JSON dict
    if raw.startswith('{'):
        try:
            data = json.loads(raw)
            return [{'name': k, 'value': str(v), 'domain': '.shopee.co.id'} for k, v in data.items()]
        except json.JSONDecodeError:
            pass
    
    # Try cookie string format: "name1=value1; name2=value2"
    cookies = []
    for part in raw.split(';'):
        part = part.strip()
        if '=' in part:
            name, _, value = part.partition('=')
            name = name.strip()
            value = value.strip()
            if name and value:
                # Determine domain from cookie name
                domain = '.shopee.co.id'
                cookies.append({'name': name, 'value': value, 'domain': domain})
    return cookies


def _cookies_to_string(cookies_list):
    """Convert cookie list to 'name=value; name=value' string."""
    return '; '.join(f"{c['name']}={c['value']}" for c in cookies_list if c.get('name') and c.get('value'))


def _make_api_call(url, cookies_str, headers=None):
    """Make API call and return (status, json_data, response_cookies).
    
    Tries: CF proxy first, then direct.
    Returns response cookies from Set-Cookie headers.
    """
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://affiliate.shopee.co.id/',
        'X-Requested-With': 'XMLHttpRequest',
    }
    if headers:
        default_headers.update(headers)
    
    # Try direct API call (captures Set-Cookie headers)
    try:
        req_headers = dict(default_headers)
        req_headers['Cookie'] = cookies_str
        resp = requests.get(url, headers=req_headers, timeout=15, allow_redirects=False)
        
        # Capture Set-Cookie from response
        response_cookies = {}
        for cookie in resp.cookies:
            response_cookies[cookie.name] = {
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain or '.shopee.co.id',
                'path': cookie.path or '/',
            }
        
        try:
            data = resp.json()
        except Exception:
            data = None
        
        return resp.status_code, data, response_cookies
    except Exception as e:
        print(f"  API call error: {e}")
        return 0, None, {}


def refresh_cookies():
    """Main refresh function. Returns refreshed cookies JSON or None."""
    
    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not cookies_raw:
        print("[Refresh] No SHOPEE_AFFILIATE_COOKIES set")
        return None
    
    cookies_list = _parse_cookies_json(cookies_raw)
    if not cookies_list:
        print("[Refresh] Could not parse cookies")
        return None
    
    print(f"[Refresh] Loaded {len(cookies_list)} cookies")
    cookies_str = _cookies_to_string(cookies_list)
    
    # ── Step 1: Test if cookies are still valid ──
    test_url = "https://affiliate.shopee.co.id/api/v3/offer/product/list?sort_type=1&page_offset=0&page_limit=1&keyword=tas"
    
    print("[Refresh] Step 1: Testing cookies via API...")
    status, data, resp_cookies = _make_api_call(test_url, cookies_str)
    print(f"[Refresh] Response: HTTP {status}")
    
    if resp_cookies:
        print(f"[Refresh] Got {len(resp_cookies)} Set-Cookie from response")
        for name in resp_cookies:
            print(f"  Set-Cookie: {name}")
    
    # Check if cookies are valid
    cookies_valid = False
    if data and isinstance(data, dict):
        code = data.get('code', -1)
        error = data.get('error', 0)
        if code == 0:
            cookies_valid = True
            print("[Refresh] Cookies are VALID")
        elif code == 30002 or (isinstance(error, int) and error > 0):
            print(f"[Refresh] Cookies EXPIRED (code={code}, error={error})")
        else:
            print(f"[Refresh] Unknown response: {str(data)[:200]}")
    
    if not cookies_valid:
        # ── Step 2: Try using shop/list endpoint (different API) ──
        shop_url = "https://affiliate.shopee.co.id/api/v3/offer/shop/list?sort_type=1&page_offset=0&page_limit=1&keyword=baju"
        print("[Refresh] Step 2: Trying shop/list API...")
        status, data, resp_cookies2 = _make_api_call(shop_url, cookies_str)
        
        if resp_cookies2:
            resp_cookies.update(resp_cookies2)
        
        if data and isinstance(data, dict) and data.get('code', -1) == 0:
            cookies_valid = True
            print("[Refresh] Cookies VALID via shop/list")
    
    if not cookies_valid:
        # ── Step 3: Try a lightweight user info endpoint ──
        user_url = "https://affiliate.shopee.co.id/api/v3/dp/user"
        print("[Refresh] Step 3: Trying user info API...")
        status, data, resp_cookies3 = _make_api_call(user_url, cookies_str)
        
        if resp_cookies3:
            resp_cookies.update(resp_cookies3)
        
        if status == 200 and data and isinstance(data, dict):
            if 'error' not in data or data.get('code', -1) == 0:
                cookies_valid = True
                print("[Refresh] Cookies VALID via user info")
    
    if not cookies_valid:
        print("[Refresh] FAILED — cookies are expired, need manual update")
        return None
    
    # ── Step 4: Merge refreshed cookies ──
    # If API returned Set-Cookie headers, merge them into existing cookies
    if resp_cookies:
        print(f"[Refresh] Merging {len(resp_cookies)} refreshed cookies")
        # Update existing cookies with new values
        existing_by_name = {c['name']: i for i, c in enumerate(cookies_list)}
        for name, new_cookie in resp_cookies.items():
            if name in existing_by_name:
                idx = existing_by_name[name]
                old_val = cookies_list[idx]['value'][:20]
                new_val = new_cookie['value'][:20]
                if old_val != new_val:
                    print(f"  Updated: {name} ({old_val}... -> {new_val}...)")
                cookies_list[idx]['value'] = new_cookie['value']
            else:
                cookies_list.append(new_cookie)
                print(f"  Added: {name}")
    
    # ── Step 5: Save refreshed cookies ──
    refreshed_json = json.dumps(cookies_list, ensure_ascii=False)
    print(f"[Refresh] Refreshed cookies: {len(refreshed_json)} chars, {len(cookies_list)} cookies")
    
    # Save to cache
    try:
        with open('/tmp/.shopee_cookies.json', 'w') as f:
            f.write(refreshed_json)
        with open('/tmp/.cookies_session_valid', 'w') as f:
            f.write('1')
        print("[Refresh] Saved to cache")
    except Exception as e:
        print(f"[Refresh] Cache save error: {e}")
    
    # Update GitHub secret if GH_PAT available
    gh_token = os.environ.get('GH_TOKEN', '')
    if gh_token:
        try:
            result = subprocess.run(
                ['gh', 'secret', 'set', 'SHOPEE_AFFILIATE_COOKIES'],
                input=refreshed_json,
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                print("[Refresh] Updated SHOPEE_AFFILIATE_COOKIES secret!")
            else:
                print(f"[Refresh] Secret update failed: {result.stderr}")
        except Exception as e:
            print(f"[Refresh] gh CLI error: {e}")
    
    # Set GITHUB_ENV for downstream steps
    github_env = os.environ.get('GITHUB_ENV', '')
    if github_env:
        with open(github_env, 'a') as f:
            f.write(f"SHOPEE_AFFILIATE_COOKIES<<EOF\n")
            f.write(refreshed_json)
            f.write(f"\nEOF\n")
        print("[Refresh] Set SHOPEE_AFFILIATE_COOKIES in GITHUB_ENV")
    
    return refreshed_json


if __name__ == '__main__':
    result = refresh_cookies()
    if result:
        print("\n[Refresh] SUCCESS — cookies refreshed!")
    else:
        print("\n[Refresh] FAILED — manual cookie update needed")
    sys.exit(0)
