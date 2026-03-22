"""
product_collector.py
Collect products + images from Shopee with MULTI-LAYER fallback.

Layers (tried in order):
  Layer 1: Shopee API with cookies (login session)
  Layer 2: Shopee public search (no login, limited)
  Layer 3: Pre-stored product bank (already downloaded from Shopee)

Output: engine/data/product_bank/{category}/{product_id}/
  ├── product.json  (name, price, desc, shopee_url, image_url)
  └── image.jpg     (verified product image)
"""

import os
import sys
import json
import time
import random
import hashlib
import requests
from PIL import Image
from io import BytesIO

# ═══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════
BANK_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'product_bank')
CATEGORIES = ['fashion', 'gadget', 'beauty', 'home', 'wellness']

# Search keywords per category (Indonesian Shopee search terms)
SEARCH_KEYWORDS = {
    'fashion': [
        'tas selempang wanita', 'jam tangan digital', 'topi bucket hat',
        'kaos oversize', 'dompet kulit pria', 'kacamata hitam UV',
        'gelang titanium', 'backpack ransel', 'hoodie polos',
        'ikat pinggang kulit', 'sneakers casual', 'sling bag mini',
        'topi baseball', 'anting titanium set', 'sweater rajut',
        'celana jogger', 'kemeja flannel', 'rok mini plisket',
        'sandal slide', 'scarf satin',
        # Tambahan
        'dress casual wanita', 'cardigan rajut', 'sepatu kets wanita',
        'clutch bag pesta', 'jaket bomber', 'celana chino pria',
        'tas ransel pria', 'kalung titanium', 'sepatu loafers',
        'belt gesper otomatis', 'tote bag kanvas', 'celana kulot',
        'kemeja linen', 'tas pinggang waist bag', 'baju polo shirt',
        'flat shoes wanita', 'jaket parasut', 'set perhiasan wanita',
        'sepatu pantofel', 'kaus kaki invisible',
    ],
    'gadget': [
        'earphone TWS bluetooth', 'powerbank 10000mAh', 'tripod HP',
        'ring light LED', 'mouse wireless', 'keyboard mechanical',
        'USB hub 3.0', 'charger fast charging', 'webcam HD',
        'speaker bluetooth portable', 'kabel type C', 'phone stand',
        'headphone gaming', 'flash drive 64GB', 'mousepad gaming XL',
        'smartwatch murah', 'card reader USB', 'cooling pad laptop',
        'mic condenser USB', 'stylus pen tablet',
        # Tambahan
        'action camera mini', 'gimbal stabilizer HP', 'monitor portable',
        'projector mini LED', 'dongle HDMI wireless', 'docking station USB C',
        'lampu klip baca LED', 'earbuds noise cancelling', 'gamepad bluetooth',
        'smart plug WiFi', 'kamera CCTV WiFi', 'tablet grafis drawing',
        'router WiFi extender', 'power strip USB', 'adaptor charger GaN',
        'portable SSD 256GB', 'VR box headset', 'drone mini murah',
        'smart TV box Android', 'kabel HDMI 4K',
    ],
    'beauty': [
        'serum vitamin C', 'sunscreen SPF 50', 'sheet mask Korea',
        'lip tint velvet', 'moisturizer aloe vera', 'toner AHA BHA',
        'eye cream retinol', 'cushion foundation', 'micellar water',
        'clay mask detox', 'essence snail mucin', 'setting spray matte',
        'cleansing balm', 'blush on powder', 'mascara waterproof',
        'lip balm tinted', 'face wash gentle', 'sleeping mask',
        'concealer stick', 'beauty blender sponge',
        # Tambahan
        'body lotion whitening', 'hair serum vitamin', 'nail art set lengkap',
        'parfum EDT wanita', 'eyebrow pencil', 'eyeliner waterproof',
        'contour palette', 'makeup brush set', 'face mist spray',
        'konjac sponge', 'peeling gel wajah', 'lip liner matte',
        'BB cream SPF', 'hair mask keratin', 'sabun muka charcoal',
        'lash serum', 'dry shampoo spray', 'body scrub coffee',
        'hand cream moisturizer', 'makeup remover balm',
    ],
    'home': [
        'rak organizer serbaguna', 'lampu LED strip USB', 'vacuum cleaner mini',
        'kotak makan 4 sekat', 'dispenser sabun otomatis', 'gorden blackout',
        'timbangan dapur digital', 'hanger lipat travel', 'lap microfiber',
        'timer dapur digital', 'sapu rubber', 'rak bumbu putar',
        'lampu tidur sensor', 'bantal memory foam', 'kotak tissue kayu',
        'tempat sampah sensor', 'aroma diffuser', 'cermin LED makeup',
        'rak sepatu portable', 'organizer laci',
        # Tambahan
        'panci set anti lengket', 'air fryer mini', 'blender portable USB',
        'pisau dapur set chef', 'talenan bambu', 'gelas ukur pyrex',
        'tempat bumbu kaca', 'cetakan es batu silikon', 'sarung bantal sofa',
        'karpet bulu halus', 'jam dinding minimalis', 'pot tanaman aesthetic',
        'rak dinding floating', 'kotak penyimpanan lipat', 'gantungan kunci dinding',
        'sprei fitted sheet', 'lilin aromaterapi', 'hook tempel dinding',
        'pemotong sayur mandoline', 'tempat sendok stainless',
    ],
    'wellness': [
        'botol minum 2 liter', 'resistance band set', 'matras yoga',
        'alat pijat leher', 'termos stainless', 'essential oil lavender',
        'foam roller', 'shaker protein', 'timbangan badan digital',
        'diffuser humidifier', 'knee support', 'jump rope skipping',
        'hand grip strengthener', 'masker olahraga', 'ankle weight',
        'pull up bar', 'ab roller wheel', 'massage gun mini',
        'yoga block busa', 'gym gloves',
        # Tambahan
        'posture corrector', 'acupressure mat', 'smart scale digital',
        'wrist wrap fitness', 'tumbler stainless 1L', 'sauna belt pembakar lemak',
        'alat terapi kaki refleksi', 'kaos olahraga dri-fit', 'dumbell set',
        'tali yoga strap', 'eye mask sleep', 'alat cukur elektrik',
        'sikat gigi elektrik', 'air purifier mini', 'heating pad elektrik',
        'koyo hangat', 'alat akupuntur pen', 'suplemen vitamin C tablet',
        'compression socks', 'elbow support brace',
    ],
}

TARGET_PER_CATEGORY = 50  # 50 × 5 categories = 250 products max per run
MIN_IMAGE_SIZE = 300      # Minimum image dimension

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
]


# ═══════════════════════════════════════════════════════════════════
#  SHOPEE SESSION (with cookies)
# ═══════════════════════════════════════════════════════════════════
def _build_shopee_session():
    """Build requests session with Shopee cookies from env."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json',
        'Accept-Language': 'id-ID,id;q=0.9,en;q=0.8',
        'Referer': 'https://shopee.co.id/',
    })

    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if not cookies_raw:
        print("  [WARN] SHOPEE_AFFILIATE_COOKIES not set — Layer 1 disabled")
        return None

    try:
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
        print(f"  [OK] Shopee session with {len(session.cookies)} cookies")
        return session
    except Exception as e:
        print(f"  [WARN] Failed to parse cookies: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
#  LAYER 1: Shopee API with Cookies
# ═══════════════════════════════════════════════════════════════════
def _shopee_search_with_cookies(session, keyword, limit=5):
    """Search Shopee with authenticated session via CF proxy."""
    if not session:
        return []

    url = 'https://shopee.co.id/api/v4/search/search_items'
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

    try:
        # Build cookie string for proxy
        cookies_str = '; '.join([f"{c.name}={c.value}" for c in session.cookies])
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'application/json',
            'Referer': f'https://shopee.co.id/search?keyword={keyword.replace(" ", "+")}',
            'X-Shopee-Language': 'id',
        }

        # Try via CF proxy
        data = None
        try:
            from shopee_proxy import proxy_get_json, is_proxy_available
            if is_proxy_available():
                from urllib.parse import urlencode
                full_url = f"{url}?{urlencode(params)}"
                status, data = proxy_get_json(full_url, headers=headers, cookies_str=cookies_str)
                if status != 200:
                    data = None
        except ImportError:
            pass

        # Direct fallback
        if data is None:
            resp = session.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"    [Layer1] HTTP {resp.status_code} for '{keyword}'")
                return []
            data = resp.json()

        items = data.get('items', [])
        products = []

        for item in items[:limit]:
            info = item.get('item_basic', {})
            shop_id = item.get('shopid', info.get('shopid', 0))
            item_id = item.get('itemid', info.get('itemid', 0))
            name = info.get('name', '')
            price = info.get('price', 0) // 100000  # Shopee price in micro-units
            image_hash = info.get('image', '')
            
            if not name or not image_hash:
                continue

            img_url = f"https://down-id.img.susercontent.com/file/{image_hash}"
            shopee_url = f"https://shopee.co.id/product/{shop_id}/{item_id}"

            products.append({
                'nama': name[:80],
                'price': f"Rp{price:,}".replace(',', '.'),
                'desc': name,
                'image_url': img_url,
                'shopee_url': shopee_url,
                'source': 'shopee_affiliate',
            })

        print(f"    [Layer1] '{keyword}' → {len(products)} products")
        return products

    except Exception as e:
        print(f"    [Layer1] Error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
#  LAYER 2: Shopee Public Search (no cookies)
# ═══════════════════════════════════════════════════════════════════
def _shopee_public_search(keyword, limit=5):
    """Search Shopee without login via CF proxy."""
    url = 'https://shopee.co.id/api/v4/search/search_items'
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
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json',
        'Referer': 'https://shopee.co.id/',
        'X-Requested-With': 'XMLHttpRequest',
    }

    try:
        # Try via CF proxy
        data = None
        try:
            from shopee_proxy import proxy_get_json, is_proxy_available
            if is_proxy_available():
                status, data = proxy_get_json(url, params=params, headers=headers)
                if status != 200:
                    data = None
        except ImportError:
            pass

        # Direct fallback
        if data is None:
            session = requests.Session()
            session.headers.update(headers)
            resp = session.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                return []
            data = resp.json()

        items = data.get('items', [])
        products = []

        for item in items[:limit]:
            info = item.get('item_basic', {})
            shop_id = item.get('shopid', info.get('shopid', 0))
            item_id = item.get('itemid', info.get('itemid', 0))
            name = info.get('name', '')
            price = info.get('price', 0) // 100000
            image_hash = info.get('image', '')

            if not name or not image_hash:
                continue

            img_url = f"https://down-id.img.susercontent.com/file/{image_hash}"
            shopee_url = f"https://shopee.co.id/product/{shop_id}/{item_id}"

            products.append({
                'nama': name[:80],
                'price': f"Rp{price:,}".replace(',', '.'),
                'desc': name,
                'image_url': img_url,
                'shopee_url': shopee_url,
                'source': 'shopee_public',
            })

        print(f"    [Layer2] '{keyword}' → {len(products)} products")
        return products

    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════
#  Shopee Category IDs for Indonesia (for category-based browsing)
# ═══════════════════════════════════════════════════════════════════
SHOPEE_CATEGORY_IDS = {
    'fashion': [
        11044568,  # Tas Wanita
        11044569,  # Sepatu Wanita
        11044567,  # Aksesoris Fashion
        11044571,  # Jam Tangan
        11044570,  # Tas Pria
    ],
    'gadget': [
        11044954,  # Elektronik
        11044956,  # Handphone & Aksesoris
        11044957,  # Komputer & Aksesoris
    ],
    'beauty': [
        11044534,  # Kecantikan
        11044535,  # Perawatan & Kesehatan
    ],
    'home': [
        11044562,  # Perlengkapan Rumah
        11044563,  # Peralatan Dapur
    ],
    'wellness': [
        11044582,  # Olahraga & Outdoor
        11044535,  # Perawatan & Kesehatan
    ],
}

# Category filter keywords (if name contains any → matches category)
CATEGORY_FILTERS = {
    'fashion': ['tas', 'sepatu', 'kaos', 'baju', 'celana', 'jam tangan', 'dompet',
                'kacamata', 'topi', 'gelang', 'cincin', 'anting', 'hoodie', 'jaket',
                'sandal', 'dress', 'kemeja', 'rok', 'sweater', 'sling bag', 'backpack'],
    'gadget': ['earphone', 'powerbank', 'charger', 'keyboard', 'mouse', 'speaker',
               'headphone', 'tripod', 'kabel', 'usb', 'webcam', 'smartwatch', 'led',
               'ring light', 'flash drive', 'adapter', 'hub', 'mic', 'holder'],
    'beauty': ['serum', 'sunscreen', 'moisturizer', 'toner', 'lip', 'cushion', 'masker',
               'cream', 'micellar', 'essence', 'clay mask', 'foundation', 'blush',
               'mascara', 'eyeliner', 'primer', 'skincare', 'makeup', 'concealer'],
    'home': ['rak', 'lampu', 'gorden', 'bantal', 'dispenser', 'lap', 'sapu', 'hanger',
             'organizer', 'vacuum', 'pisau', 'timbangan', 'dapur', 'cermin', 'pot',
             'aroma', 'timer', 'karpet', 'sprei', 'selimut'],
    'wellness': ['yoga', 'resistance', 'botol minum', 'shaker', 'pijat', 'essential oil',
                 'dumbell', 'foam roller', 'timbangan', 'gym', 'olahraga', 'sport',
                 'fitness', 'protein', 'vitamin', 'termos'],
}


# ═══════════════════════════════════════════════════════════════════
#  LAYER 3: Shopee Recommend API (daily discover - bypasses search block)
# ═══════════════════════════════════════════════════════════════════
def _shopee_recommend_discover(category, limit=10):
    """Fetch products from Shopee Recommend API (daily_discover_main).
    This endpoint is DIFFERENT from search_items — not blocked by error 90309999.
    Returns popular products, filtered by category keywords."""
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json',
        'Referer': 'https://shopee.co.id/',
        'X-Shopee-Language': 'id',
        'X-Requested-With': 'XMLHttpRequest',
    }

    # Build cookie string from env
    cookies_str = ''
    cookies_raw = os.environ.get('SHOPEE_AFFILIATE_COOKIES', '')
    if cookies_raw:
        try:
            cookies = json.loads(cookies_raw)
            if isinstance(cookies, list):
                cookies_str = '; '.join([f"{c.get('name','')}={c.get('value','')}"
                                         for c in cookies if c.get('name')])
            elif isinstance(cookies, dict):
                cookies_str = '; '.join([f'{k}={v}' for k, v in cookies.items()])
        except Exception:
            pass

    cat_ids = SHOPEE_CATEGORY_IDS.get(category, [])
    cat_filters = [kw.lower() for kw in CATEGORY_FILTERS.get(category, [])]
    products = []

    # Try daily discover (popular items)
    bundles = ['daily_discover_main', 'daily_discover_tab']
    for bundle in bundles:
        if len(products) >= limit:
            break

        url = f"https://shopee.co.id/api/v4/recommend/recommend?bundle={bundle}&limit=60&offset=0"

        try:
            data = None
            try:
                from shopee_proxy import proxy_get_json, is_proxy_available
                if is_proxy_available():
                    status, data = proxy_get_json(url, headers=headers, cookies_str=cookies_str)
                    if status != 200:
                        data = None
            except ImportError:
                pass

            if data is None:
                if cookies_str:
                    headers['Cookie'] = cookies_str
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()

            if not data:
                continue

            # Parse recommend response (different format from search)
            sections = data.get('data', {}).get('sections', [])
            for section in sections:
                items = section.get('data', {}).get('item', [])
                for item_wrap in items:
                    if len(products) >= limit:
                        break
                    item = item_wrap if isinstance(item_wrap, dict) else {}
                    # Could be nested in 'item_basic' or direct
                    info = item.get('item_basic', item)
                    name = info.get('name', '')
                    if not name:
                        continue

                    # Filter by category keywords
                    name_lower = name.lower()
                    if cat_filters and not any(kw in name_lower for kw in cat_filters):
                        continue

                    shop_id = info.get('shopid', 0)
                    item_id = info.get('itemid', 0)
                    price = info.get('price', 0)
                    if price > 100000:
                        price = price // 100000
                    image_hash = info.get('image', '')
                    if not image_hash or not item_id:
                        continue

                    img_url = f"https://down-id.img.susercontent.com/file/{image_hash}"
                    shopee_url = f"https://shopee.co.id/product/{shop_id}/{item_id}"

                    products.append({
                        'nama': name[:80],
                        'price': f"Rp{price:,}".replace(',', '.'),
                        'desc': name,
                        'image_url': img_url,
                        'shopee_url': shopee_url,
                        'source': 'shopee_recommend',
                    })

        except Exception as e:
            print(f"    [Layer3] {bundle} error: {e}")

    print(f"    [Layer3] Recommend API → {len(products)} products (category={category})")
    return products


# ═══════════════════════════════════════════════════════════════════
#  LAYER 4: Shopee Category Page Scrape (HTML → embedded JSON)
# ═══════════════════════════════════════════════════════════════════
def _shopee_category_scrape(category, limit=10):
    """Scrape products from Shopee category page HTML.
    Shopee embeds product data in page's JSON. Different endpoint from search API."""
    import re as _re
    cat_ids = SHOPEE_CATEGORY_IDS.get(category, [])
    if not cat_ids:
        return []

    products = []
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'id-ID,id;q=0.9',
        'Referer': 'https://shopee.co.id/',
    }

    for cat_id in cat_ids[:2]:  # Max 2 category pages
        if len(products) >= limit:
            break

        url = f"https://shopee.co.id/api/v4/search/search_items?by=pop&limit=20&match_id={cat_id}&newest=0&order=desc&page_type=search&version=2"

        try:
            data = None
            try:
                from shopee_proxy import proxy_get_json, is_proxy_available
                if is_proxy_available():
                    status, data = proxy_get_json(url, headers={
                        'User-Agent': random.choice(USER_AGENTS),
                        'Accept': 'application/json',
                        'Referer': f'https://shopee.co.id/mall/cat/{cat_id}',
                        'X-Shopee-Language': 'id',
                    })
                    if status != 200:
                        data = None
            except ImportError:
                pass

            if not data:
                continue

            items = data.get('items', [])
            for item in items[:limit]:
                info = item.get('item_basic', {})
                name = info.get('name', '')
                shop_id = info.get('shopid', item.get('shopid', 0))
                item_id = info.get('itemid', item.get('itemid', 0))
                price = info.get('price', 0)
                if price > 100000:
                    price = price // 100000
                image_hash = info.get('image', '')

                if not name or not image_hash:
                    continue

                img_url = f"https://down-id.img.susercontent.com/file/{image_hash}"
                shopee_url = f"https://shopee.co.id/product/{shop_id}/{item_id}"

                products.append({
                    'nama': name[:80],
                    'price': f"Rp{price:,}".replace(',', '.'),
                    'desc': name,
                    'image_url': img_url,
                    'shopee_url': shopee_url,
                    'source': 'shopee_category',
                })

            time.sleep(random.uniform(2.0, 4.0))

        except Exception as e:
            print(f"    [Layer4] Cat {cat_id} error: {e}")

    print(f"    [Layer4] Category scrape → {len(products)} products")
    return products




# ═══════════════════════════════════════════════════════════════════
#  DOWNLOAD + SAVE PRODUCT
# ═══════════════════════════════════════════════════════════════════
def _download_product_image(image_url, save_path):
    """Download and validate product image."""
    try:
        resp = requests.get(image_url, timeout=15, headers={
            'User-Agent': random.choice(USER_AGENTS),
            'Referer': 'https://shopee.co.id/',
        })
        if resp.status_code != 200:
            return False

        img = Image.open(BytesIO(resp.content))
        w, h = img.size
        if w < MIN_IMAGE_SIZE or h < MIN_IMAGE_SIZE:
            print(f"      Image too small: {w}x{h}")
            return False

        # Convert to RGB and save
        img = img.convert('RGB')
        # Resize to at least 1080 wide
        if w < 1080:
            scale = 1080 / w
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        img.save(save_path, 'JPEG', quality=90)
        return True

    except Exception as e:
        print(f"      Download failed: {e}")
        return False


def _generate_product_id(name, category):
    """Generate unique product ID from name + category."""
    raw = f"{category}_{name}".lower().strip()
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    prefix = category[0].upper()
    return f"{prefix}{h}"


def _to_affiliate_url(url):
    """Convert any Shopee URL to affiliate link using AFFILIATE_ID_SHOPEE."""
    aff_id = os.environ.get('AFFILIATE_ID_SHOPEE', '')
    if not aff_id or not url:
        return url  # keep original if no affiliate ID

    # Already an affiliate link? keep it
    if 'utm_source=an_' in url or 'affiliate' in url:
        return url

    # Extract shop_id and item_id from regular product URL
    import re
    m = re.search(r'/product/(\d+)/(\d+)', url)
    if m:
        shop_id, item_id = m.group(1), m.group(2)
        return (f"https://shopee.co.id/universal-link/product/{shop_id}/{item_id}"
                f"?utm_source=an_{aff_id}&utm_medium=affiliates"
                f"&utm_campaign=-&utm_content=----")

    return url  # can't parse → keep original


def _save_product(product, category, image_path):
    """Save product info + image to product bank."""
    pid = _generate_product_id(product['nama'], category)
    product_dir = os.path.join(BANK_DIR, category, pid)
    os.makedirs(product_dir, exist_ok=True)

    # Convert URL to affiliate link
    shopee_url = _to_affiliate_url(product.get('shopee_url', ''))

    # Save product info
    info = {
        'produk_id': pid,
        'nama': product['nama'],
        'price': product['price'],
        'desc': product['desc'],
        'shopee_url': shopee_url,
        'image_url': product.get('image_url', ''),
        'category': category,
        'source': product.get('source', 'unknown'),
        'collected_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }

    info_path = os.path.join(product_dir, 'product.json')
    with open(info_path, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    # Copy/move image
    img_dest = os.path.join(product_dir, 'image.jpg')
    if image_path and os.path.exists(image_path):
        import shutil
        shutil.copy2(image_path, img_dest)
    elif product.get('image_url'):
        _download_product_image(product['image_url'], img_dest)

    return pid, os.path.exists(os.path.join(product_dir, 'image.jpg'))


# ═══════════════════════════════════════════════════════════════════
#  MAIN COLLECTOR
# ═══════════════════════════════════════════════════════════════════
def count_bank(category):
    """Count AVAILABLE products in bank (excludes already-used ones)."""
    cat_dir = os.path.join(BANK_DIR, category)
    if not os.path.exists(cat_dir):
        return 0

    # Load used product IDs from dedup tracker
    used_ids = set()
    try:
        from dedup_tracker import _load as _load_dedup
        data = _load_dedup()
        for acct_data in data.values():
            used_ids.update(acct_data.keys())
    except Exception:
        pass

    count = 0
    for d in os.listdir(cat_dir):
        dirpath = os.path.join(cat_dir, d)
        if not os.path.isdir(dirpath):
            continue
        if not os.path.exists(os.path.join(dirpath, 'image.jpg')):
            continue
        if d in used_ids:
            continue  # skip — already used for video
        count += 1
    return count


def collect_products(categories=None, target=None):
    """Main collection function. Tries all layers per category.
    
    Priority order:
      Layer 0: Shopee Affiliate API (affiliate.shopee.co.id) — PRIMARY
      Layer 1+2: Affiliate shop/list with broader keywords
      Layer 3: Shopee recommend API (fallback alternate endpoint)
      Layer 4: Shopee category browse (fallback alternate endpoint)
    """
    print("=" * 60)
    print("  PRODUCT COLLECTOR — Multi-Layer (Affiliate-First)")
    print("=" * 60)

    if categories is None:
        categories = CATEGORIES
    if target is None:
        target = TARGET_PER_CATEGORY

    # ── Pre-flight: Check if cookies are SET (not if they're valid) ──
    # Health check is diagnostic only — does NOT block collection.
    # Each layer handles its own errors gracefully.
    has_cookies = bool(os.environ.get('SHOPEE_AFFILIATE_COOKIES', ''))
    if not has_cookies:
        print("\n  ⚠️ SHOPEE_AFFILIATE_COOKIES not set — Layer 0/1/2 will be skipped")
    else:
        print(f"  ✅ SHOPEE_AFFILIATE_COOKIES set ({len(os.environ.get('SHOPEE_AFFILIATE_COOKIES', ''))} chars)")
        # Diagnostic only — log health but don't block
        try:
            from shopee_affiliate import check_cookies_health
            health = check_cookies_health()
            if not health:
                print("  ⚠️ Health check returned False — but will TRY layers anyway")
        except ImportError:
            pass
        except Exception as e:
            print(f"  ⚠️ Health check error: {e} — will TRY layers anyway")

    # Build Shopee session for legacy search (rarely used)
    shopee_session = _build_shopee_session()

    stats = {cat: {'existing': 0, 'new': 0, 'failed': 0} for cat in categories}

    for category in categories:
        print(f"\n--- Category: {category.upper()} ---")
        existing = count_bank(category)
        stats[category]['existing'] = existing

        if existing >= target:
            print(f"  Already have {existing} products (target={target}). Skipping.")
            continue

        need = target - existing
        print(f"  Have {existing}, need {need} more...")
        collected = 0

        # ══════════════════════════════════════════════════════════
        #  LAYER 0: Shopee Affiliate API (PRIMARY)
        # ══════════════════════════════════════════════════════════
        if not has_cookies:
            print(f"  [SKIP] Layer 0 — no cookies set")
        else:
            try:
                from shopee_affiliate import collect_affiliate_products
                aff_products = collect_affiliate_products(category, target=need)
                for prod in aff_products:
                    if collected >= need:
                        break
                    pid = _generate_product_id(prod['nama'], category)
                    product_dir = os.path.join(BANK_DIR, category, pid)
                    if os.path.exists(os.path.join(product_dir, 'image.jpg')):
                        continue
                    import tempfile
                    tmp_img = os.path.join(tempfile.gettempdir(), f'{pid}_temp.jpg')
                    if prod.get('image_url') and _download_product_image(prod['image_url'], tmp_img):
                        pid, ok = _save_product(prod, category, tmp_img)
                        if ok:
                            print(f"    ✓ [Affiliate] {prod['nama'][:40]}")
                            collected += 1
                            stats[category]['new'] += 1
                        else:
                            stats[category]['failed'] += 1
                        try:
                            os.remove(tmp_img)
                        except Exception:
                            pass
                    else:
                        stats[category]['failed'] += 1
                if collected > 0:
                    print(f"  → Layer 0 (Affiliate): +{collected} products")
            except ImportError:
                print("  [SKIP] shopee_affiliate module not found")
            except Exception as e:
                print(f"  [WARN] Affiliate API error: {e}")

        # ══════════════════════════════════════════════════════════
        #  LAYER 1+2: More Affiliate Shop searches (different keywords)
        #  Uses PROVEN /api/v3/offer/shop/list → get_shop_products
        #  (product/list endpoint also blocked by 90309999)
        # ══════════════════════════════════════════════════════════
        if collected < need and has_cookies:
            try:
                from shopee_affiliate import get_affiliate_shops, \
                    get_shop_products, _build_affiliate_session, \
                    build_product_affiliate_link, AFFILIATE_KEYWORDS
            except ImportError:
                get_affiliate_shops = None

            if get_affiliate_shops:
                aff_session = _build_affiliate_session()
                # Use SEARCH_KEYWORDS (broader terms, different from Layer 0)
                search_kws = SEARCH_KEYWORDS.get(category, [])
                random.shuffle(search_kws)

                for keyword in search_kws[:3]:
                    if collected >= need:
                        break

                    print(f"\n  [Layer1+2] Affiliate shops: '{keyword}'...")
                    time.sleep(random.uniform(1.0, 2.0))

                    shops = get_affiliate_shops(keyword, session=aff_session, limit=10)
                    if not shops:
                        continue

                    # Sort by commission, pick top 3
                    def _csort(s):
                        r = s.get('commission_rate', '0%').replace('%', '').replace(',', '.')
                        try:
                            return float(r)
                        except ValueError:
                            return 0
                    shops = sorted(shops, key=_csort, reverse=True)[:3]

                    for shop in shops:
                        if collected >= need:
                            break
                        shop_id = shop.get('shop_id', '')
                        shop_name = shop.get('shop_name', '')
                        long_link = shop.get('long_link', '')
                        commission = shop.get('commission_rate', '0%')

                        time.sleep(random.uniform(1.0, 2.0))
                        shop_prods = get_shop_products(shop_id, limit=4)

                        for sp in shop_prods:
                            if collected >= need:
                                break
                            img_hash = sp.get('image_hash', '')
                            img_url = f"https://down-id.img.susercontent.com/file/{img_hash}" if img_hash else ''
                            aff_link = build_product_affiliate_link(
                                shop_id, sp.get('item_id', 0), long_link)
                            price_val = sp.get('price', 0)

                            prod = {
                                'nama': sp.get('name', '')[:80],
                                'price': f"Rp{price_val:,}".replace(',', '.') if price_val else 'Lihat harga',
                                'desc': sp.get('name', ''),
                                'image_url': img_url,
                                'shopee_url': aff_link,
                                'source': 'shopee_affiliate',
                                'commission': commission,
                                'shop_name': shop_name,
                            }

                            pid = _generate_product_id(prod['nama'], category)
                            product_dir = os.path.join(BANK_DIR, category, pid)
                            if os.path.exists(os.path.join(product_dir, 'image.jpg')):
                                continue

                            import tempfile
                            tmp_img = os.path.join(tempfile.gettempdir(), f'{pid}_temp.jpg')

                            if img_url and _download_product_image(img_url, tmp_img):
                                pid, ok = _save_product(prod, category, tmp_img)
                                if ok:
                                    print(f"    ✓ Saved: {prod['nama'][:40]} [affiliate_shop]")
                                    collected += 1
                                    stats[category]['new'] += 1
                                else:
                                    stats[category]['failed'] += 1
                                try:
                                    os.remove(tmp_img)
                                except Exception:
                                    pass
                            else:
                                stats[category]['failed'] += 1

                        # Shop fallback REMOVED — store logos/commission are NOT products

        # ══════════════════════════════════════════════════════════
        #  LAYER 5: HTML Scraper (NO cookies needed!)
        # ══════════════════════════════════════════════════════════
        if collected < need:
            try:
                from shopee_scraper import scrape_search
                remaining = need - collected
                print(f"\n  [Layer5] HTML scraper (no cookies needed)...")
                category_keywords = SEARCH_KEYWORDS.get(category, [category])
                random.shuffle(category_keywords)  # randomize to get variety
                for kw in category_keywords[:30]:   # try up to 30 keywords (of 40)
                    if collected >= need:
                        break
                    scraped = scrape_search(kw, limit=10)  # 10 per keyword
                    for prod in scraped:
                        if collected >= need:
                            break
                        pid = _generate_product_id(prod["nama"], category)
                        product_dir = os.path.join(BANK_DIR, category, pid)
                        if os.path.exists(os.path.join(product_dir, "image.jpg")):
                            continue
                        import tempfile
                        tmp_img = os.path.join(tempfile.gettempdir(), f"{pid}_temp.jpg")
                        if prod.get("image_url") and _download_product_image(prod["image_url"], tmp_img):
                            pid, ok = _save_product(prod, category, tmp_img)
                            if ok:
                                print(f"    OK Saved: {prod['nama'][:40]} [scraper]")
                                collected += 1
                                stats[category]["new"] += 1
                            else:
                                stats[category]["failed"] += 1
                            try:
                                os.remove(tmp_img)
                            except Exception:
                                pass
                    time.sleep(random.uniform(1.0, 2.0))
            except ImportError:
                print("  [Layer5] shopee_scraper not available")
            except Exception as e:
                print(f"  [Layer5] Error: {e}")

        # ── FALLBACK: Layer 3+4 if still need more ──
        if collected < need:
            remaining = need - collected
            print(f"\n  [FALLBACK] Need {remaining} more. Trying recommend + category browse...")

            # Layer 3: Recommend API (daily discover — different endpoint)
            alt_products = _shopee_recommend_discover(category, limit=remaining)

            # Layer 4: Category browse (if recommend didn't get enough)
            if len(alt_products) < remaining:
                time.sleep(random.uniform(2.0, 4.0))
                more = _shopee_category_scrape(category, limit=remaining - len(alt_products))
                alt_products.extend(more)

            # Process alternative products
            for prod in alt_products:
                if collected >= need:
                    break

                pid = _generate_product_id(prod['nama'], category)
                product_dir = os.path.join(BANK_DIR, category, pid)
                if os.path.exists(os.path.join(product_dir, 'image.jpg')):
                    continue

                import tempfile
                tmp_img = os.path.join(tempfile.gettempdir(), f'{pid}_temp.jpg')
                img_url = prod.get('image_url', '')

                if img_url and _download_product_image(img_url, tmp_img):
                    pid, ok = _save_product(prod, category, tmp_img)
                    if ok:
                        print(f"    ✓ Saved: {prod['nama'][:40]} [{prod['source']}]")
                        collected += 1
                        stats[category]['new'] += 1
                    else:
                        stats[category]['failed'] += 1
                    try:
                        os.remove(tmp_img)
                    except Exception:
                        pass
                else:
                    stats[category]['failed'] += 1

        print(f"  → {category}: +{collected} new products")

    # Summary
    print("\n" + "=" * 60)
    print("  COLLECTION SUMMARY")
    print("=" * 60)
    total_new = 0
    for cat in categories:
        s = stats[cat]
        total_now = s['existing'] + s['new']
        total_new += s['new']
        print(f"  {cat:12s}: {total_now:3d} products ({s['new']} new, {s['failed']} failed)")
    print(f"  {'TOTAL':12s}: {total_new} new products collected")
    print("=" * 60)

    return stats


def export_bank_to_csv(output_file=None):
    """Export AVAILABLE product bank to CSV for the video pipeline.
    Skips: already-used products (dedup). Rp0 prices use 'Lihat di Shopee' fallback."""
    if output_file is None:
        output_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'produk.csv')
    import csv

    # Load used product IDs from dedup tracker — these are permanently excluded
    used_ids = set()
    try:
        from dedup_tracker import _load as _load_dedup
        data = _load_dedup()
        for acct_data in data.values():
            used_ids.update(acct_data.keys())
    except Exception:
        pass
    if used_ids:
        print(f"  [EXPORT] Filtering out {len(used_ids)} already-used products")



    all_products = []
    skipped = {'no_image': 0, 'used': 0, 'no_price': 0}

    for category in CATEGORIES:
        cat_dir = os.path.join(BANK_DIR, category)
        if not os.path.exists(cat_dir):
            continue

        for pid_dir in os.listdir(cat_dir):
            # SKIP already-used products (permanent — never reuse for video)
            if pid_dir in used_ids:
                skipped['used'] += 1
                continue

            product_dir = os.path.join(cat_dir, pid_dir)
            info_file = os.path.join(product_dir, 'product.json')
            image_file = os.path.join(product_dir, 'image.jpg')

            if not os.path.exists(info_file) or not os.path.exists(image_file):
                skipped['no_image'] += 1
                continue

            try:
                with open(info_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)

                img_url = info.get('image_url', '')

                # Get price — try multiple fields
                price_str = info.get('harga', info.get('price', ''))
                if isinstance(price_str, (int, float)):
                    price_str = f"Rp{int(price_str):,}".replace(',', '.')

                # Rp0 or empty → use fallback text (do NOT skip the product)
                if price_str in ('Rp0', 'Rp0.0', '', '0', 'Rp0.0.0'):
                    price_str = 'Lihat di Shopee'

                # Map to pipeline-compatible column names
                product = {
                    'produk_id': info.get('produk_id', pid_dir),
                    'nama': info.get('nama', info.get('name', 'Produk')),
                    'deskripsi_singkat': info.get('deskripsi_singkat', info.get('desc', '')),
                    'harga': price_str,
                    'rating': info.get('rating', 0),
                    'terjual': info.get('terjual', info.get('sold', 0)),
                    'shopee_url': info.get('shopee_url', ''),
                    'tokopedia_url': '',
                    'image_url': img_url,
                    'category': info.get('category', category),
                }
                all_products.append(product)
            except Exception as e:
                print(f"  [EXPORT] Error reading {pid_dir}: {e}")
                continue

    if any(skipped.values()):
        print(f"  Skipped: {skipped['used']} used, "
              f"{skipped['no_image']} no image, "
              f"{skipped['no_price']} bad price")

    if not all_products:
        print("No valid products in bank after filtering!")
        return 0

    # Write CSV with pipeline-compatible columns
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    fieldnames = ['produk_id', 'nama', 'deskripsi_singkat', 'harga', 'rating', 'terjual',
                  'shopee_url', 'tokopedia_url', 'image_url', 'category']
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_products)

    print(f"Exported {len(all_products)} valid products to {output_file}")
    return len(all_products)


def copy_bank_images_to_pipeline(images_dir=None):
    """Copy product bank images to pipeline images directory."""
    if images_dir is None:
        images_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'images')
    import shutil
    os.makedirs(images_dir, exist_ok=True)
    copied = 0

    for category in CATEGORIES:
        cat_dir = os.path.join(BANK_DIR, category)
        if not os.path.exists(cat_dir):
            continue

        for pid_dir in os.listdir(cat_dir):
            product_dir = os.path.join(cat_dir, pid_dir)
            src_img = os.path.join(product_dir, 'image.jpg')
            if not os.path.exists(src_img):
                continue

            dst_img = os.path.join(images_dir, f"{pid_dir}.jpg")
            if not os.path.exists(dst_img):
                shutil.copy2(src_img, dst_img)
                copied += 1

    print(f"Copied {copied} images to {images_dir}")
    return copied


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Product Collector')
    parser.add_argument('--category', type=str, default=None,
                        help='Collect for specific category only')
    parser.add_argument('--target', type=int, default=TARGET_PER_CATEGORY,
                        help='Target products per category')
    parser.add_argument('--export', action='store_true',
                        help='Export bank to CSV + copy images')
    parser.add_argument('--status', action='store_true',
                        help='Show current bank status')
    args = parser.parse_args()

    if args.status:
        print("Product Bank Status:")
        for cat in CATEGORIES:
            print(f"  {cat}: {count_bank(cat)} products")
        sys.exit(0)

    if args.export:
        n = export_bank_to_csv()
        copy_bank_images_to_pipeline()
        print(f"Done. {n} products exported.")
        sys.exit(0)

    cats = [args.category] if args.category else None
    stats = collect_products(categories=cats, target=args.target)

    # Auto-export after collection
    n_exported = export_bank_to_csv()
    n_copied = copy_bank_images_to_pipeline()

    # ── EXIT CODE: fail if 0 products in bank ──
    total_new = sum(s['new'] for s in stats.values()) if stats else 0
    total_bank = sum(count_bank(c) for c in CATEGORIES)

    print(f"\n{'=' * 60}")
    print(f"  FINAL STATUS")
    print(f"  New products collected : {total_new}")
    print(f"  Total products in bank: {total_bank}")
    print(f"  Exported to CSV       : {n_exported}")
    print(f"  Images copied         : {n_copied}")
    print(f"{'=' * 60}")

    if total_bank == 0 and n_exported == 0:
        print("\n  ❌ FAIL: Bank is empty — no products available for pipeline!")
        print("  Check: SHOPEE_AFFILIATE_COOKIES, CF_PROXY_URL, CF_PROXY_KEY")
        sys.exit(1)
    elif total_new == 0 and total_bank > 0:
        print(f"\n  ⚠️ No NEW products, but bank has {total_bank} existing products.")
        print("  Pipeline can still use existing bank stock.")
    else:
        print(f"\n  ✅ Collection complete!")
