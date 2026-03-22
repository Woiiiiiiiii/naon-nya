"""
shopee_scraper.py
Scrape products from Shopee via HTML __NEXT_DATA__ — NO cookies, NO login, NO API key.

Usage:
  from shopee_scraper import scrape_search, scrape_product_page

Flow:
  1. Search: GET https://shopee.co.id/search?keyword=xxx → extract __NEXT_DATA__
  2. Product page: GET product URL → extract __NEXT_DATA__
  3. Affiliate link: resolve short link → get real URL → scrape
"""

import re
import json
import time
import random
import requests
from urllib.parse import urlencode, quote_plus

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
]


def _get_session():
    """Create a requests session mimicking a real browser."""
    s = requests.Session()
    ua = random.choice(USER_AGENTS)
    s.headers.update({
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://shopee.co.id/',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Ch-Ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
    })
    return s


def _extract_next_data(html):
    """Extract __NEXT_DATA__ JSON from Shopee HTML page."""
    match = re.search(
        r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
        html, re.DOTALL
    )
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


def _try_fetch(url, session=None, via_proxy=True):
    """Fetch URL content. Try direct first, then via CF proxy if blocked."""
    if session is None:
        session = _get_session()
    
    # Try direct
    try:
        resp = session.get(url, timeout=20)
        if resp.status_code == 200 and len(resp.text) > 1000:
            return resp.text
        print(f"    [Scraper] Direct: HTTP {resp.status_code}, len={len(resp.text)}")
    except Exception as e:
        print(f"    [Scraper] Direct error: {e}")
    
    # Try via CF proxy
    if via_proxy:
        try:
            from shopee_proxy import proxy_get_json, is_proxy_available
            import os
            proxy_url = os.environ.get('CF_PROXY_URL', '')
            proxy_key = os.environ.get('CF_PROXY_KEY', '')
            if proxy_url and proxy_key:
                # Use proxy for HTML fetch
                proxy_resp = requests.post(
                    proxy_url,
                    json={
                        'url': url,
                        'method': 'GET',
                        'headers': dict(session.headers),
                    },
                    headers={
                        'X-Proxy-Key': proxy_key,
                        'Content-Type': 'application/json',
                    },
                    timeout=20,
                )
                if proxy_resp.status_code == 200:
                    return proxy_resp.text
        except Exception:
            pass
    
    return None


def scrape_search(keyword, limit=10):
    """Scrape Shopee search results via HTML.
    
    Returns list of product dicts: {nama, price, desc, image_url, shopee_url, source}
    """
    print(f"    [Scraper] Searching: '{keyword}'")
    session = _get_session()
    
    # Method 1: Try Shopee search API directly (works without cookies for basic results)
    search_api = f"https://shopee.co.id/api/v4/search/search_items"
    params = {
        'by': 'relevancy',
        'keyword': keyword,
        'limit': limit,
        'newest': 0,
        'order': 'desc',
        'page_type': 'search',
        'scenario': 'PAGE_GLOBAL_SEARCH',
        'version': 2,
    }
    
    products = []
    
    # Try search API via proxy (better success rate from GitHub Actions)
    try:
        from shopee_proxy import proxy_get_json, is_proxy_available
        if is_proxy_available():
            status, data = proxy_get_json(
                search_api,
                params=params,
                headers={
                    'User-Agent': random.choice(USER_AGENTS),
                    'Accept': 'application/json',
                    'Referer': f'https://shopee.co.id/search?keyword={quote_plus(keyword)}',
                    'X-Shopee-Language': 'id',
                    'X-Requested-With': 'XMLHttpRequest',
                },
            )
            if status == 200 and data:
                items = data.get('items', [])
                for item in items[:limit]:
                    prod = _parse_search_item(item)
                    if prod:
                        products.append(prod)
                if products:
                    print(f"    [Scraper] API proxy: {len(products)} products")
                    return products
                else:
                    print(f"    [Scraper] API proxy: 200 OK but 0 parseable products")
            else:
                print(f"    [Scraper] API proxy: status={status}, no data")
    except ImportError:
        print("    [Scraper] shopee_proxy not available")
    except Exception as e:
        print(f"    [Scraper] API proxy error: {e}")
    
    # Method 2: Scrape search page HTML → __NEXT_DATA__
    search_url = f"https://shopee.co.id/search?keyword={quote_plus(keyword)}"
    html = _try_fetch(search_url, session)
    
    if html:
        data = _extract_next_data(html)
        if data:
            try:
                # Navigate the __NEXT_DATA__ structure for search results
                page_props = data.get('props', {}).get('pageProps', {})
                
                # Try different paths where Shopee stores search data
                items = (
                    page_props.get('searchResult', {}).get('items', []) or
                    page_props.get('initialData', {}).get('items', []) or
                    page_props.get('data', {}).get('items', []) or
                    []
                )
                
                for item in items[:limit]:
                    prod = _parse_search_item(item)
                    if prod:
                        products.append(prod)
                
                if products:
                    print(f"    [Scraper] HTML search: {len(products)} products")
                    return products
            except Exception as e:
                print(f"    [Scraper] Parse error: {e}")
    
    # Method 3: Try direct API (no proxy, no cookies)
    try:
        api_url = f"{search_api}?{urlencode(params)}"
        resp = session.get(api_url, headers={
            'Accept': 'application/json',
            'X-Shopee-Language': 'id',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f'https://shopee.co.id/search?keyword={quote_plus(keyword)}',
        }, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('items', [])
            for item in items[:limit]:
                prod = _parse_search_item(item)
                if prod:
                    products.append(prod)
            if products:
                print(f"    [Scraper] API direct: {len(products)} products")
                return products
    except Exception as e:
        print(f"    [Scraper] API direct error: {e}")
    
    print(f"    [Scraper] No results for '{keyword}'")
    return []


def _parse_search_item(item):
    """Parse a search result item into product dict."""
    info = item.get('item_basic', item)
    name = info.get('name', '')
    if not name:
        return None
    
    shop_id = info.get('shopid', item.get('shopid', 0))
    item_id = info.get('itemid', item.get('itemid', 0))
    
    price = info.get('price', 0)
    if price > 100000:
        price = price // 100000
    
    image_hash = info.get('image', '')
    if not image_hash:
        # Try images list
        images = info.get('images', [])
        if images:
            image_hash = images[0]
    
    if not image_hash:
        return None
    
    img_url = f"https://down-id.img.susercontent.com/file/{image_hash}"
    shopee_url = f"https://shopee.co.id/product/{shop_id}/{item_id}"
    
    return {
        'nama': name[:80],
        'price': f"Rp{price:,}".replace(',', '.'),
        'desc': name,
        'image_url': img_url,
        'shopee_url': shopee_url,
        'source': 'shopee_scraper',
    }


def scrape_product_page(url):
    """Scrape a single product page via __NEXT_DATA__.
    
    Args:
        url: Product URL or affiliate short link
    
    Returns: product dict or None
    """
    session = _get_session()
    
    # Resolve short links
    if 's.shopee.co.id' in url or 'shope.ee' in url:
        try:
            resp = session.get(url, allow_redirects=True, timeout=10)
            url = resp.url
            print(f"    [Scraper] Resolved to: {url}")
        except Exception as e:
            print(f"    [Scraper] Redirect error: {e}")
            return None
    
    html = _try_fetch(url, session)
    if not html:
        return None
    
    data = _extract_next_data(html)
    if not data:
        print("    [Scraper] No __NEXT_DATA__ found")
        return None
    
    try:
        page_props = data.get('props', {}).get('pageProps', {})
        item_info = page_props.get('itemInfo', {}).get('item', {})
        
        if not item_info:
            # Try alternative path
            item_info = page_props.get('initialData', {}).get('item', {})
        
        if not item_info:
            return None
        
        name = item_info.get('name', '')
        price = item_info.get('price', 0)
        if price > 100000:
            price = price // 100000
        
        image = item_info.get('image', '')
        if not image:
            images = item_info.get('images', [])
            if images:
                image = images[0]
        
        img_url = f"https://cf.shopee.co.id/file/{image}" if image else ''
        
        shop_id = item_info.get('shopid', 0)
        item_id = item_info.get('itemid', 0)
        
        return {
            'nama': name[:80],
            'price': f"Rp{price:,}".replace(',', '.'),
            'desc': name,
            'image_url': img_url,
            'shopee_url': f"https://shopee.co.id/product/{shop_id}/{item_id}",
            'source': 'shopee_scraper',
        }
    except Exception as e:
        print(f"    [Scraper] Parse error: {e}")
        return None


# ── Quick test ──
if __name__ == '__main__':
    print("Testing Shopee scraper...\n")
    
    keywords = ['tas wanita', 'sepatu pria', 'skincare']
    for kw in keywords:
        products = scrape_search(kw, limit=3)
        for p in products:
            print(f"  {p['nama'][:50]} — {p['price']}")
        print()
        time.sleep(1)
