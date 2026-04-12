"""
url_shortener.py
Shorten Shopee affiliate URLs via TinyURL API.

Per-channel TinyURL API keys (same mapping as Gemini):
  yt_1 → TINYURL_API_KEY_1    yt_4 → TINYURL_API_KEY_4    fb_1 → TINYURL_API_KEY_7
  yt_2 → TINYURL_API_KEY_2    yt_5 → TINYURL_API_KEY_5
  yt_3 → TINYURL_API_KEY_3    tt_1 → TINYURL_API_KEY_6

Fallback: if TinyURL fails, returns original URL (pipeline never breaks).
Cache: shortened URLs cached in-memory to avoid duplicate API calls.
"""
import os
import requests
import time

# Per-channel key index (matches Gemini mapping)
ACCOUNT_KEY_MAP = {
    'yt_1': 1, 'yt_2': 2, 'yt_3': 3, 'yt_4': 4, 'yt_5': 5,
    'tt_1': 6, 'fb_1': 7,
    # Category aliases
    'fashion': 1, 'gadget': 2, 'beauty': 3, 'home': 4, 'wellness': 5,
}

# In-memory cache: {long_url: short_url}
_cache = {}


def _get_api_key(account_id):
    """Get TinyURL API key for a specific channel."""
    key_index = ACCOUNT_KEY_MAP.get(account_id)
    if not key_index:
        return None
    return os.environ.get(f'TINYURL_API_KEY_{key_index}', '')


def shorten_url(url, account_id=None):
    """Shorten a URL via TinyURL API.

    Args:
        url: The long URL to shorten
        account_id: Channel ID (yt_1..yt_5, tt_1, fb_1) for key lookup

    Returns:
        Shortened URL (https://tinyurl.com/xxx) or original URL on failure.
        Pipeline NEVER breaks — fallback to original URL on any error.
    """
    if not url or 'shopee' not in url:
        return url

    # Check cache first
    if url in _cache:
        return _cache[url]

    api_key = _get_api_key(account_id)
    if not api_key:
        return url  # No key → keep original

    try:
        resp = requests.post(
            'https://api.tinyurl.com/create',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'url': url,
                'domain': 'tinyurl.com',
            },
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            short_url = data.get('data', {}).get('tiny_url', '')
            if short_url:
                _cache[url] = short_url
                print(f"    [URL] Shortened → {short_url}")
                # Rate limit: small delay between API calls
                time.sleep(1)
                return short_url

        # Log non-200 but don't break
        print(f"    [URL] TinyURL {resp.status_code}: {resp.text[:80]}")

    except Exception as e:
        print(f"    [URL] TinyURL error: {e}")

    # Fallback: return original URL (pipeline never breaks)
    return url
