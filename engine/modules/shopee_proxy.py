"""
shopee_proxy.py
Route Shopee requests through Cloudflare Worker to bypass IP blocking.

Uses:
  CF_PROXY_URL  = Worker URL (e.g., https://shopee-proxy.<account>.workers.dev)
  CF_PROXY_KEY  = Secret key for authentication (= CF_PROXY_KEY_API value)

If CF_PROXY_URL is not set, falls back to direct requests (will be blocked).
"""
import os
import json
import requests
from io import BytesIO

_PROXY_URL = None
_PROXY_KEY = None
_initialized = False


def _init():
    """Initialize proxy config from environment."""
    global _PROXY_URL, _PROXY_KEY, _initialized
    if _initialized:
        return
    _initialized = True

    _PROXY_URL = os.environ.get('CF_PROXY_URL', '').rstrip('/')
    _PROXY_KEY = os.environ.get('CF_PROXY_KEY', os.environ.get('CF_PROXY_KEY_API', ''))

    if _PROXY_URL and _PROXY_KEY:
        print(f"  [Proxy] CF Workers proxy enabled: {_PROXY_URL[:40]}...")
    else:
        if not _PROXY_URL:
            print("  [Proxy] CF_PROXY_URL not set — direct requests (may be blocked)")
        elif not _PROXY_KEY:
            print("  [Proxy] CF_PROXY_KEY not set — direct requests (may be blocked)")


def is_proxy_available():
    """Check if CF proxy is configured."""
    _init()
    return bool(_PROXY_URL and _PROXY_KEY)


def proxy_get(url, headers=None, cookies_str='', timeout=15):
    """Make a GET request through CF Worker proxy.

    Returns: requests.Response-like object with .status_code, .text, .content, .json()
    Falls back to direct request if proxy unavailable.
    """
    _init()

    if not _PROXY_URL or not _PROXY_KEY:
        # Direct request fallback
        req_headers = headers or {}
        if cookies_str:
            req_headers['Cookie'] = cookies_str
        return requests.get(url, headers=req_headers, timeout=timeout)

    # Route through CF Worker
    payload = {
        'url': url,
        'method': 'GET',
        'headers': headers or {},
        'cookies': cookies_str,
    }

    try:
        resp = requests.post(
            f"{_PROXY_URL}/proxy",
            json=payload,
            headers={
                'X-Proxy-Key': _PROXY_KEY,
                'Content-Type': 'application/json',
            },
            timeout=timeout + 5,  # Extra buffer for proxy overhead
        )
        return resp
    except Exception as e:
        print(f"    [Proxy] Error: {e}, falling back to direct")
        req_headers = headers or {}
        if cookies_str:
            req_headers['Cookie'] = cookies_str
        return requests.get(url, headers=req_headers, timeout=timeout)


def proxy_get_json(url, params=None, headers=None, cookies_str='', timeout=15):
    """Make a GET request expecting JSON response, through CF proxy.

    Handles URL params construction.
    Returns: (status_code, json_data or None)
    """
    _init()

    # Build full URL with params
    if params:
        from urllib.parse import urlencode
        full_url = f"{url}?{urlencode(params)}"
    else:
        full_url = url

    resp = proxy_get(full_url, headers=headers, cookies_str=cookies_str, timeout=timeout)

    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, None


def proxy_download_image(url, save_path, min_size=5000, timeout=15):
    """Download an image through CF proxy.

    Returns: True if image saved successfully, False otherwise.
    """
    _init()

    headers = {
        'Referer': 'https://shopee.co.id/',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
    }

    try:
        resp = proxy_get(url, headers=headers, timeout=timeout)

        if resp.status_code != 200:
            return False

        if len(resp.content) < min_size:
            return False

        # Validate it's actually an image
        from PIL import Image
        img = Image.open(BytesIO(resp.content))
        img.verify()  # Will raise if not valid image

        # Save
        with open(save_path, 'wb') as f:
            f.write(resp.content)
        return True

    except Exception:
        return False
