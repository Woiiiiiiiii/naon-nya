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
    ],
    'gadget': [
        'earphone TWS bluetooth', 'powerbank 10000mAh', 'tripod HP',
        'ring light LED', 'mouse wireless', 'keyboard mechanical',
        'USB hub 3.0', 'charger fast charging', 'webcam HD',
        'speaker bluetooth portable', 'kabel type C', 'phone stand',
        'headphone gaming', 'flash drive 64GB', 'mousepad gaming XL',
        'smartwatch murah', 'card reader USB', 'cooling pad laptop',
        'mic condenser USB', 'stylus pen tablet',
    ],
    'beauty': [
        'serum vitamin C', 'sunscreen SPF 50', 'sheet mask Korea',
        'lip tint velvet', 'moisturizer aloe vera', 'toner AHA BHA',
        'eye cream retinol', 'cushion foundation', 'micellar water',
        'clay mask detox', 'essence snail mucin', 'setting spray matte',
        'cleansing balm', 'blush on powder', 'mascara waterproof',
        'lip balm tinted', 'face wash gentle', 'sleeping mask',
        'concealer stick', 'beauty blender sponge',
    ],
    'home': [
        'rak organizer serbaguna', 'lampu LED strip USB', 'vacuum cleaner mini',
        'kotak makan 4 sekat', 'dispenser sabun otomatis', 'gorden blackout',
        'timbangan dapur digital', 'hanger lipat travel', 'lap microfiber',
        'timer dapur digital', 'sapu rubber', 'rak bumbu putar',
        'lampu tidur sensor', 'bantal memory foam', 'kotak tissue kayu',
        'tempat sampah sensor', 'aroma diffuser', 'cermin LED makeup',
        'rak sepatu portable', 'organizer laci',
    ],
    'wellness': [
        'botol minum 2 liter', 'resistance band set', 'matras yoga',
        'alat pijat leher', 'termos stainless', 'essential oil lavender',
        'foam roller', 'shaker protein', 'timbangan badan digital',
        'diffuser humidifier', 'knee support', 'jump rope skipping',
        'hand grip strengthener', 'masker olahraga', 'ankle weight',
        'pull up bar', 'ab roller wheel', 'massage gun mini',
        'yoga block busa', 'gym gloves',
    ],
}

TARGET_PER_CATEGORY = 20  # Aim for 20 products per category
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

    cookies_raw = os.environ.get('SHOPEE_COOKIES', '')
    if not cookies_raw:
        print("  [WARN] SHOPEE_COOKIES not set — Layer 1 disabled")
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
                'source': 'shopee_cookies',
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


def _save_product(product, category, image_path):
    """Save product info + image to product bank."""
    pid = _generate_product_id(product['nama'], category)
    product_dir = os.path.join(BANK_DIR, category, pid)
    os.makedirs(product_dir, exist_ok=True)

    # Save product info
    info = {
        'produk_id': pid,
        'nama': product['nama'],
        'price': product['price'],
        'desc': product['desc'],
        'shopee_url': product.get('shopee_url', ''),
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
    """Count products in bank for a category."""
    cat_dir = os.path.join(BANK_DIR, category)
    if not os.path.exists(cat_dir):
        return 0
    return len([d for d in os.listdir(cat_dir)
                if os.path.isdir(os.path.join(cat_dir, d))
                and os.path.exists(os.path.join(cat_dir, d, 'image.jpg'))])


def collect_products(categories=None, target=None):
    """Main collection function. Tries all layers per category."""
    print("=" * 60)
    print("  PRODUCT COLLECTOR — Multi-Layer")
    print("=" * 60)

    if categories is None:
        categories = CATEGORIES
    if target is None:
        target = TARGET_PER_CATEGORY

    # Build Shopee session (Layer 1)
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

        keywords = SEARCH_KEYWORDS.get(category, [])
        random.shuffle(keywords)  # Randomize to get variety
        collected = 0

        for keyword in keywords:
            if collected >= need:
                break

            print(f"\n  Searching: '{keyword}'...")
            time.sleep(random.uniform(1.5, 3.0))  # Polite delay

            products = []

            # Layer 1: Shopee with cookies
            if shopee_session and not products:
                products = _shopee_search_with_cookies(shopee_session, keyword, limit=3)

            # Layer 2: Shopee public
            if not products:
                time.sleep(1)
                products = _shopee_public_search(keyword, limit=3)

            # Layer 1+2 gagal → skip keyword (bank data dari run sebelumnya tetap available)
            if not products:
                print(f"    [SKIP] No Shopee results for '{keyword}'")

            # Process found products
            for prod in products:
                if collected >= need:
                    break

                # Check if already in bank
                pid = _generate_product_id(prod['nama'], category)
                product_dir = os.path.join(BANK_DIR, category, pid)
                if os.path.exists(os.path.join(product_dir, 'image.jpg')):
                    continue

                # Download image to temp
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

                    # Clean up temp
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


def export_bank_to_csv(output_file='engine/data/produk.csv'):
    """Export product bank to CSV for the video pipeline.
    Column names match scrape_produk.py format for pipeline compatibility.
    Skips garbage data (Rp0 prices, Pexels/Pixabay images)."""
    import csv

    # No price recovery from hardcoded data — products with Rp0 are skipped
    fallback_prices = {}

    all_products = []
    skipped = {'no_price': 0, 'pexels': 0, 'no_image': 0}

    for category in CATEGORIES:
        cat_dir = os.path.join(BANK_DIR, category)
        if not os.path.exists(cat_dir):
            continue

        for pid_dir in os.listdir(cat_dir):
            product_dir = os.path.join(cat_dir, pid_dir)
            info_file = os.path.join(product_dir, 'product.json')
            image_file = os.path.join(product_dir, 'image.jpg')

            if not os.path.exists(info_file) or not os.path.exists(image_file):
                skipped['no_image'] += 1
                continue

            try:
                with open(info_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)

                # SKIP garbage: Pexels/Pixabay/Unsplash images
                img_url = info.get('image_url', '')
                if any(x in img_url for x in ['pexels.com', 'pixabay.com', 'unsplash.com']):
                    skipped['pexels'] += 1
                    continue

                # Get price — try multiple fields
                price_str = info.get('harga', info.get('price', ''))
                if isinstance(price_str, (int, float)):
                    price_str = f"Rp{int(price_str):,}".replace(',', '.')

                # SKIP garbage: Rp0 price
                if price_str in ('Rp0', 'Rp0.0', '', '0'):
                    # Try to recover price from fallback
                    nama_key = info.get('nama', '').lower().strip()
                    recovered = fallback_prices.get(nama_key, '')
                    if recovered:
                        price_str = recovered
                    else:
                        skipped['no_price'] += 1
                        continue

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
            except Exception:
                continue

    if skipped['pexels'] or skipped['no_price']:
        print(f"  Skipped garbage: {skipped['pexels']} Pexels images, "
              f"{skipped['no_price']} Rp0 prices, {skipped['no_image']} no image")

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


def copy_bank_images_to_pipeline(images_dir='engine/data/images'):
    """Copy product bank images to pipeline images directory."""
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
    collect_products(categories=cats, target=args.target)

    # Auto-export after collection
    export_bank_to_csv()
    copy_bank_images_to_pipeline()
