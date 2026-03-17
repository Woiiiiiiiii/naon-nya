"""
scrape_produk.py
Scrape products for ALL 5 categories (fashion, gadget, beauty, home, wellness).
Each product is tagged with its category so batch_manager can assign correctly.

Output: engine/data/produk.csv with 'category' column

Strategy per category:
1. Try Shopee search API with cookies (CF proxy) for real product+affiliate links
2. Try Shopee public search API (CF proxy)
3. If ALL fail → skip category (NO fake data, NO hardcoded products)

IMPORTANT: ALL products MUST come from live Shopee API.
  - This ensures affiliate links point to real, purchasable products
  - Product images come from Shopee CDN (verified available)
  - No Pexels/Pixabay/hardcoded data allowed
"""
import os
import sys
import json
import csv
import datetime
import random
import requests
import yaml

# Import categories from category_router
sys.path.insert(0, os.path.dirname(__file__))
try:
    from category_router import CATEGORY_KEYWORDS, YOUTUBE_CATEGORIES
except ImportError:
    CATEGORY_KEYWORDS = {}
    YOUTUBE_CATEGORIES = {}

try:
    from dedup_tracker import is_product_used
except ImportError:
    def is_product_used(product_id, account_id=None): return False

# All 5 categories to scrape
CATEGORIES = ['fashion', 'gadget', 'beauty', 'home', 'wellness']


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'engine_config.yaml')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


def get_affiliate_url(product_name, affiliate_id):
    """Generate Shopee search URL with affiliate tag."""
    query = product_name.replace(' ', '+')
    return f"https://shopee.co.id/search?keyword={query}&af_id={affiliate_id}"

# ═══════════════════════════════════════════════════════════════════
#  SHOPEE SESSION (with cookies — same pattern as product_collector)
# ═══════════════════════════════════════════════════════════════════
_shopee_session = None

def _build_shopee_session():
    """Build authenticated Shopee session from SHOPEE_COOKIES env var."""
    global _shopee_session
    if _shopee_session is not None:
        return _shopee_session

    cookies_raw = os.environ.get('SHOPEE_COOKIES', '')
    if not cookies_raw:
        _shopee_session = False
        return False

    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': random.choice(user_agents),
            'Accept': 'application/json',
            'Accept-Language': 'id-ID,id;q=0.9,en;q=0.8',
            'Referer': 'https://shopee.co.id/',
        })
        cookies = json.loads(cookies_raw)
        if isinstance(cookies, list):
            for c in cookies:
                name = c.get('name', '')
                value = c.get('value', '')
                domain = c.get('domain', '.shopee.co.id')
                if name and value:
                    session.cookies.set(name, value, domain=domain)
        elif isinstance(cookies, dict):
            for name, value in cookies.items():
                session.cookies.set(name, str(value), domain='.shopee.co.id')
        _shopee_session = session
        print(f"  [OK] Shopee session with {len(session.cookies)} cookies")
        return session
    except Exception:
        _shopee_session = False
        return False


# Rotate User-Agents
user_agents = [
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.101 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def search_shopee_cookies(keyword, limit=5):
    """Tier 3: Shopee search with authenticated cookies (direct or via proxy).
    Retry once with backoff if 200-but-0-items (rate limit response)."""
    session = _build_shopee_session()
    if not session:
        return None

    url = "https://shopee.co.id/api/v4/search/search_items"
    cookies_str = '; '.join([f"{c.name}={c.value}" for c in session.cookies])
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "application/json",
        "Referer": f"https://shopee.co.id/search?keyword={keyword.replace(' ', '+')}",
        "X-Shopee-Language": "id",
    }

    import time as _t

    for attempt in range(2):  # 2 attempts: initial + 1 retry
        params = {
            "by": "relevancy", "keyword": keyword, "limit": limit,
            "newest": random.randint(0, 20),  # Vary offset to avoid cache
            "order": "desc", "page_type": "search",
            "scenario": "PAGE_GLOBAL_SEARCH", "version": 2,
        }
        delay = random.uniform(2.0, 4.0) if attempt == 0 else random.uniform(4.0, 6.0)
        _t.sleep(delay)

        try:
            # Try via CF proxy first (more reliable than direct from CI)
            try:
                from shopee_proxy import proxy_get_json, is_proxy_available
                if is_proxy_available():
                    from urllib.parse import urlencode
                    full_url = f"{url}?{urlencode(params)}"
                    status, data = proxy_get_json(full_url, headers=headers, cookies_str=cookies_str)
                    if status == 200 and data:
                        items = data.get("items", [])
                        if items:
                            print(f"    [Tier3-Cookies+Proxy] '{keyword}' -> {len(items)} products")
                            return items
            except ImportError:
                pass

            # Direct fallback with cookies
            resp = session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items:
                    print(f"    [Tier3-Cookies] '{keyword}' -> {len(items)} products")
                    return items

            if attempt == 0:
                print(f"    [Tier3] attempt 1 got 0 items, retrying with backoff...")

        except Exception as e:
            print(f"    [Tier3] Cookies exception: {e}")
            if attempt == 0:
                _t.sleep(3)
                continue
            return None

    return None


def search_shopee_proxy(keyword, limit=5):
    """Tier 1: Shopee search API via CF Worker proxy (no cookies).
    Retries once with longer backoff on 200-but-0-items (Shopee rate limit)."""
    try:
        from shopee_proxy import proxy_get_json, is_proxy_available
        if not is_proxy_available():
            print(f"    [Tier1] CF proxy not available (CF_PROXY_URL/CF_PROXY_KEY missing)")
            return None
    except ImportError:
        print(f"    [Tier1] shopee_proxy module not found")
        return None

    url = "https://shopee.co.id/api/v4/search/search_items"
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "application/json",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        "Referer": f"https://shopee.co.id/search?keyword={keyword.replace(' ', '+')}",
        "X-Requested-With": "XMLHttpRequest",
        "X-Shopee-Language": "id",
    }

    import time as _t

    for attempt in range(2):  # 2 attempts: initial + 1 retry
        params = {
            "by": "relevancy", "keyword": keyword, "limit": limit,
            "newest": random.randint(0, 50),
            "order": "desc", "page_type": "search",
            "scenario": "PAGE_GLOBAL_SEARCH", "version": 2,
        }
        # Longer delay: 2-4s first try, 5-8s retry (avoid Shopee rate limit)
        delay = random.uniform(2.0, 4.0) if attempt == 0 else random.uniform(5.0, 8.0)
        _t.sleep(delay)

        try:
            status, data = proxy_get_json(url, params=params, headers=headers)
            if status == 200 and data:
                items = data.get("items", [])
                if items:
                    print(f"    [Tier1-CFProxy] '{keyword}' -> {len(items)} products")
                    return items
                else:
                    error = data.get('error', data.get('error_msg', ''))
                    if attempt == 0:
                        print(f"    [Tier1] 0 items (rate limit?), retrying with backoff...")
                        continue
                    print(f"    [Tier1] HTTP {status} but 0 items after retry. error={error}")
            elif status == 403:
                print(f"    [Tier1] Shopee 403 via CF proxy (Worker IP blocked)")
                return None  # No retry for 403
            elif status == 401:
                print(f"    [Tier1] CF proxy 401 (key mismatch!)")
                return None  # No retry for auth failure
            else:
                snippet = str(data)[:100] if data else 'None'
                print(f"    [Tier1] HTTP {status}. Response: {snippet}")
        except Exception as e:
            print(f"    [Tier1] Exception: {e}")
            if attempt == 0:
                continue
    return None


def search_shopee(keyword, limit=5):
    """Tier 2: Direct Shopee public search API (no proxy, no cookies).
    Skipped automatically on CI (GitHub Actions IP always blocked by Shopee)."""
    # Auto-skip on CI — GitHub Actions IPs are ALWAYS blocked by Shopee
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        return None  # Don't waste time, go straight to Tier 3

    url = "https://shopee.co.id/api/v4/search/search_items"
    params = {
        "by": "relevancy", "keyword": keyword, "limit": limit,
        "newest": random.randint(0, 50),
        "order": "desc", "page_type": "search",
        "scenario": "PAGE_GLOBAL_SEARCH", "version": 2,
    }

    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "application/json",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        "Referer": f"https://shopee.co.id/search?keyword={keyword.replace(' ', '+')}",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua-platform": '"Android"',
    }
    try:
        import time as _t
        _t.sleep(random.uniform(1.0, 2.0))
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 403:
            print(f"    [Tier2] Direct API: HTTP 403 (IP blocked by Shopee)")
            return None
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            if items:
                print(f"    [Tier2-DirectAPI] '{keyword}' -> {len(items)} products")
                return items
            else:
                print(f"    [Tier2] HTTP 200 but 0 items")
        else:
            print(f"    [Tier2] HTTP {resp.status_code}")
        return None
    except Exception as e:
        print(f"    [Tier2] Exception: {e}")
        return None


def extract_product_info(item, affiliate_id, category):
    """Extract product info from Shopee search result."""
    item_basic = item.get("item_basic", item)
    item_id = item_basic.get("itemid", "")
    shop_id = item_basic.get("shopid", "")
    name = item_basic.get("name", "Produk").replace("\n", " ").strip()
    if len(name) > 80:
        name = name[:77] + "..."

    price_raw = item_basic.get("price", 0)
    price = int(price_raw) // 100000 if price_raw > 100000 else int(price_raw)
    price_str = f"Rp{price:,}".replace(",", ".")

    image_id = item_basic.get("image", "")
    image_url = f"https://down-id.img.susercontent.com/file/{image_id}" if image_id else ""

    rating = round(item_basic.get("item_rating", {}).get("rating_star", 0), 1)
    sold = item_basic.get("sold", item_basic.get("historical_sold", 0))
    desc = f"{name} - {price_str} | Rating {rating}\u2b50 | Terjual {sold}+"

    aff_url = f"https://shopee.co.id/product/{shop_id}/{item_id}?af_id={affiliate_id}"

    return {
        "produk_id": f"p{item_id}",
        "nama": name, "deskripsi_singkat": desc,
        "harga": price_str, "rating": rating, "terjual": sold,
        "shopee_url": aff_url, "tokopedia_url": "",
        "image_url": image_url,
        "category": category,
    }


def scrape_category(category, affiliate_id, target_count=3):
    """Scrape products for a single category using 3 tiers with retry.

    Tier 1: CF Proxy → Shopee API (with retry + backoff on rate limit)
    Tier 2: Direct → Shopee API (auto-skipped on CI — IP always blocked)
    Tier 3: Shopee Cookies via proxy (with retry + backoff)

    Each tier retries 1x on 200-but-0-items (anti-bot rate limit).
    Inter-keyword delay: 3-5s to avoid triggering Shopee rate limit.
    """
    import time as _t
    products = []
    seen_ids = set()
    tier_failures = {'tier1': 0, 'tier2': 0, 'tier3': 0}

    cat_keywords = CATEGORY_KEYWORDS.get(category, {}).get('scrape', [])
    if not cat_keywords:
        cat_keywords = [category]

    keywords = cat_keywords[:]
    random.shuffle(keywords)

    for kw_idx, keyword in enumerate(keywords[:6]):  # Max 6 keywords (was 8)
        if len(products) >= target_count:
            break

        # Inter-keyword delay (skip first keyword)
        if kw_idx > 0:
            inter_delay = random.uniform(3.0, 5.0)
            _t.sleep(inter_delay)

        # ── Tier 1: CF Proxy (with retry built into function) ──
        items = search_shopee_proxy(keyword, limit=5)

        # ── Tier 2: Direct Shopee API (auto-skips on CI) ──
        if items is None:
            tier_failures['tier1'] += 1
            items = search_shopee(keyword, limit=5)

        # ── Tier 3: Shopee Cookies (with retry built into function) ──
        if items is None:
            tier_failures['tier2'] += 1
            items = search_shopee_cookies(keyword, limit=5)

        if items is None:
            tier_failures['tier3'] += 1
            print(f"    [ALL TIERS FAILED] No results for '{keyword}'")
            continue

        for item in items:
            if len(products) >= target_count:
                break
            try:
                product = extract_product_info(item, affiliate_id, category)
                if product["produk_id"] in seen_ids or not product["image_url"]:
                    continue
                # DEDUP: skip products already used in ANY previous video
                if is_product_used(product["produk_id"]):
                    print(f"      [DEDUP] Already used: {product['nama'][:40]}")
                    continue
                if product["terjual"] < 10:
                    continue
                # REJECT non-Shopee images
                if 'susercontent.com' not in product["image_url"]:
                    print(f"      [REJECT] Non-Shopee image: {product['image_url'][:50]}")
                    continue
                seen_ids.add(product["produk_id"])
                products.append(product)
                print(f"      [OK] {product['nama'][:50]} ({product['harga']})")
            except Exception:
                continue

    if not products:
        print(f"    [EMPTY] No products for {category} — all tiers failed")
        print(f"    Tier stats: T1(proxy)={tier_failures['tier1']}fail T2(direct)={tier_failures['tier2']}fail T3(cookies)={tier_failures['tier3']}fail")
        print(f"    Checklist: CF_PROXY_URL? CF_PROXY_KEY? SHOPEE_COOKIES expired?")

    return products


def scrape_products(output_file, config):
    """Scrape products for ALL categories from LIVE Shopee API.

    Flow:
      1. Load existing produk.csv (from product_collector --export if available)
      2. Try scraping fresh products from Shopee API
      3. If Shopee succeeds → use fresh products for that category
      4. If Shopee blocked → KEEP existing bank products (if valid Shopee data)
      5. Save merged result

    IMPORTANT: Only real Shopee products are accepted. Bank products with
    Pexels/Pixabay URLs or Rp0 prices are rejected as garbage.
    """
    affiliate_id = config.get("shopee", {}).get("affiliate_id", "11344941723")
    products_per_category = config.get("scrape", {}).get("products_per_category", 3)

    print(f"=== Shopee Product Scraper (Live API Only) ===")
    print(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %A')}")
    print(f"Categories: {', '.join(CATEGORIES)}")
    print(f"Products per category: {products_per_category}")
    print(f"Affiliate ID: {affiliate_id}")

    # ── DIAGNOSTIC: check all required env vars ──
    proxy_url = os.environ.get('CF_PROXY_URL', '')
    proxy_key = os.environ.get('CF_PROXY_KEY', '')
    cookies = os.environ.get('SHOPEE_COOKIES', '')
    print(f"\n  [ENV DIAGNOSTIC]")
    print(f"  CF_PROXY_URL:   {'SET (' + proxy_url[:30] + '...)' if proxy_url else 'NOT SET'}")
    print(f"  CF_PROXY_KEY:   {'SET (' + str(len(proxy_key)) + ' chars)' if proxy_key else 'NOT SET'}")
    print(f"  SHOPEE_COOKIES: {'SET (' + str(len(cookies)) + ' chars)' if cookies else 'NOT SET'}")
    if not proxy_url:
        print(f"  WARNING: CF_PROXY_URL not set -- Shopee API will be blocked (403)!")
    if not cookies:
        print(f"  WARNING: SHOPEE_COOKIES not set -- cookies search disabled!")


    # Step 1: Load existing bank data (from product_collector --export)
    existing_by_cat = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cat = row.get('category', '')
                    if cat:
                        existing_by_cat.setdefault(cat, []).append(row)
            total_existing = sum(len(v) for v in existing_by_cat.values())
            print(f"  Loaded {total_existing} existing products from bank")
        except Exception as e:
            print(f"  [WARN] Could not load existing CSV: {e}")

    # Step 2: Scrape fresh products per category
    all_products = []
    stats = {'fresh': 0, 'bank': 0, 'skipped': 0}

    for category in CATEGORIES:
        print(f"\n  --- Category: {category.upper()} ---")
        bank_products = existing_by_cat.get(category, [])
        print(f"    Bank products available: {len(bank_products)}")

        # Try scraping fresh from Shopee API
        cat_products = scrape_category(category, affiliate_id, products_per_category)

        # VALIDATE bank products — reject Pexels/Pixabay/Rp0 garbage
        valid_bank = [
            p for p in bank_products
            if not any(x in str(p.get('image_url', '')) for x in ['pexels.com', 'pixabay.com', 'unsplash.com'])
            and str(p.get('harga', '')) not in ('Rp0', 'Rp0.0', '', '0')
            and 'susercontent.com' in str(p.get('image_url', ''))  # Must be Shopee CDN
        ]
        if len(valid_bank) < len(bank_products):
            garbage = len(bank_products) - len(valid_bank)
            print(f"    [CLEAN] Filtered out {garbage} garbage from bank (non-Shopee)")
            bank_products = valid_bank

        if cat_products:
            # Fresh scrape succeeded — use fresh Shopee products
            all_products.extend(cat_products)
            stats['fresh'] += len(cat_products)
            print(f"    [OK] Using {len(cat_products)} FRESH products from Shopee API")
        elif bank_products:
            # Scrape failed but bank has VALID Shopee data
            all_products.extend(bank_products)
            stats['bank'] += len(bank_products)
            print(f"    [BANK] Using {len(bank_products)} BANK products (valid Shopee data)")
        else:
            # No products at all — skip this category
            stats['skipped'] += 1
            print(f"    [SKIP] SKIPPED {category} -- no Shopee products available")
            print(f"      Fix: ensure CF_PROXY_URL + SHOPEE_COOKIES are set in CI secrets")

    # Save merged result
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    fieldnames = ["produk_id", "nama", "deskripsi_singkat", "harga", "rating", "terjual",
                   "shopee_url", "tokopedia_url", "image_url", "category"]

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_products)

    print(f"\n=== Scraping Complete (Live API Only) ===")
    print(f"  Fresh from Shopee: {stats['fresh']}")
    print(f"  Kept from bank:    {stats['bank']}")
    print(f"  Categories skipped: {stats['skipped']}")
    for cat in CATEGORIES:
        count = sum(1 for p in all_products if p.get('category') == cat)
        print(f"  {cat}: {count} products")
    print(f"  Total: {len(all_products)} products saved to {output_file}")

    if stats['skipped'] > 0:
        print(f"\n  WARNING: {stats['skipped']} categories had NO products!")
        print(f"  This means Shopee API is blocked and CF proxy may not be working.")
        print(f"  Check GitHub secrets: CF_PROXY_URL, CF_PROXY_KEY_API, SHOPEE_COOKIES")

    return all_products


if __name__ == "__main__":
    config = load_config()
    scrape_products("engine/data/produk.csv", config)
