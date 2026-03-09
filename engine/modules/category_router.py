"""
category_router.py
Central routing module — maps categories to accounts, platforms, and keywords.

Used by:
  - batch_manager.py → assign products to correct accounts
  - generate_music.py → select mood per category
  - background_manager.py → fetch matching backgrounds
  - image_compositor.py → style per category
  - generate_video_*.py → template & copywriting selection
  - generate_*_metadata.py → hashtags & descriptions
"""
import datetime

# ═══════════════════════════════════════════════════════════════════
#  YOUTUBE ACCOUNTS — each has a fixed category
# ═══════════════════════════════════════════════════════════════════
YOUTUBE_CATEGORIES = {
    'yt_1': {
        'category': 'fashion',
        'label': 'Fashion & Aksesoris',
        'channel': 'PantauProduk',
    },
    'yt_2': {
        'category': 'gadget',
        'label': 'Gadget & Tech',
        'channel': 'CekVideo',
    },
    'yt_3': {
        'category': 'beauty',
        'label': 'Skincare & Beauty',
        'channel': 'ReviewKilat',
    },
    'yt_4': {
        'category': 'home',
        'label': 'Home & Living',
        'channel': 'IntipProduk',
    },
    'yt_5': {
        'category': 'wellness',
        'label': 'Health & Wellness',
        'channel': 'TinjauCepat',
    },
}

# ═══════════════════════════════════════════════════════════════════
#  TIKTOK & FACEBOOK — ALTERNATING CATEGORIES by day
#  TikTok: fashion (odd days) ↔ beauty (even days)
#  Facebook: home (odd days) ↔ gadget (even days)
# ═══════════════════════════════════════════════════════════════════
def _get_tt_category():
    """TikTok alternates fashion ↔ beauty based on day of month."""
    day = datetime.datetime.now().day
    if day % 2 == 1:  # Odd days
        return {'account_id': 'tt_1', 'category': 'fashion', 'label': 'Fashion & Aksesoris'}
    else:              # Even days
        return {'account_id': 'tt_1', 'category': 'beauty', 'label': 'Skincare & Beauty'}

def _get_fb_category():
    """Facebook alternates home ↔ gadget based on day of month."""
    day = datetime.datetime.now().day
    if day % 2 == 1:  # Odd days
        return {'account_id': 'fb_1', 'category': 'home', 'label': 'Home & Living'}
    else:              # Even days
        return {'account_id': 'fb_1', 'category': 'gadget', 'label': 'Gadget & Tech'}

# Legacy compat — dynamic properties
TIKTOK_ACCOUNT = _get_tt_category()
FACEBOOK_ACCOUNT = _get_fb_category()

# ═══════════════════════════════════════════════════════════════════
#  KEYWORD MAPPING PER CATEGORY
#  Used by: scraper, background_manager, music, copywriting
# ═══════════════════════════════════════════════════════════════════
CATEGORY_KEYWORDS = {
    'fashion': {
        'scrape': ['tas wanita', 'sepatu sneakers', 'kaos oversize', 'hoodie',
                   'jam tangan', 'topi bucket', 'gelang couple', 'kacamata hitam',
                   'dompet kulit pria', 'ikat pinggang', 'sling bag', 'backpack ransel',
                   'celana jogger', 'jaket jeans', 'sweater rajut', 'rok plisket',
                   'sandal slide', 'anting titanium', 'kalung rantai', 'cincin couple',
                   'kemeja flanel', 'vest rompi', 'cardigan rajut', 'celana chino',
                   'scarf satin', 'beanie hat', 'belt canvas', 'tas pinggang waistbag',
                   'kaos polo', 'dress casual', 'overall jumpsuit', 'celana kulot'],
        'background': ['fashion product flatlay table', 'clothing on wooden table',
                       'fashion accessories table top view', 'white marble surface fashion',
                       'minimalist table product display'],
        'video_bg': ['lifestyle cafe street aesthetic', 'fashion runway slow motion',
                     'city street style cinematic', 'boutique interior'],
        'music_mood': 'happy',
        'hashtags': ['#fashion', '#ootd', '#style', '#outfit', '#shopee',
                     '#affiliate', '#recommended', '#viral'],
        'accent_color': (255, 64, 129),   # Pink
    },
    'gadget': {
        'scrape': ['powerbank', 'earbuds TWS', 'charger fast charging', 'tripod HP',
                   'keyboard mechanical', 'mouse wireless', 'ring light', 'holder HP',
                   'USB hub', 'kabel data type C', 'webcam HD', 'speaker bluetooth',
                   'headphone gaming', 'flash drive 64GB', 'mousepad gaming',
                   'adaptor laptop universal', 'smart watch', 'drone mini',
                   'action camera', 'microphone kondenser', 'monitor portable',
                   'SSD external', 'cooling pad laptop', 'stylus pen tablet',
                   'projector mini', 'keyboard wireless', 'earphone sport',
                   'power strip USB', 'card reader', 'HDMI splitter', 'VR headset'],
        'background': ['desk setup workspace top view', 'gadget on dark desk',
                       'tech product on table', 'laptop desk flatlay',
                       'wooden desk technology workspace'],
        'video_bg': ['desk setup cinematic workspace', 'technology abstract motion',
                     'computer screen typing closeup', 'neon lights technology'],
        'music_mood': 'energetic',
        'hashtags': ['#gadget', '#tech', '#review', '#unboxing', '#shopee',
                     '#affiliate', '#recommended', '#viral'],
        'accent_color': (0, 176, 255),    # Cyan
    },
    'beauty': {
        'scrape': ['serum wajah', 'sunscreen SPF', 'moisturizer', 'toner wajah',
                   'lip tint', 'cushion foundation', 'masker wajah', 'eye cream',
                   'micellar water', 'essence snail', 'clay mask', 'cleansing balm',
                   'setting spray', 'blush on', 'mascara waterproof', 'eyeliner pen',
                   'foundation cair', 'concealer stick', 'face mist', 'sleeping mask',
                   'body lotion', 'hair serum', 'facial wash', 'exfoliating toner',
                   'bb cream SPF', 'primer makeup', 'eyebrow pencil', 'lip balm',
                   'contour palette', 'beauty blender sponge', 'makeup remover'],
        'background': ['vanity table cosmetics flatlay', 'skincare on marble surface',
                       'beauty product display table', 'pink surface makeup',
                       'bathroom shelf products'],
        'video_bg': ['slow motion flowers glitter beauty', 'pink petals falling',
                     'water drops closeup aesthetic', 'golden shimmer bokeh'],
        'music_mood': 'chill',
        'hashtags': ['#skincare', '#beauty', '#review', '#glowup', '#shopee',
                     '#affiliate', '#recommended', '#viral'],
        'accent_color': (233, 30, 99),    # Rose
    },
    'home': {
        'scrape': ['rak organizer', 'lampu LED', 'gorden blackout', 'bantal tidur',
                   'dispenser sabun', 'tempat bumbu', 'lap microfiber', 'sapu magic',
                   'kotak penyimpanan', 'hanger lipat', 'timer dapur', 'timbangan dapur',
                   'vacuum cleaner mini', 'alas makan silikon', 'pisau dapur set',
                   'rak sepatu', 'cermin LED', 'kotak tisu', 'pot tanaman',
                   'lampu meja belajar', 'aroma diffuser', 'jam dinding',
                   'tatakan gelas', 'tempat sikat gigi', 'rak handuk', 'sprei fitted',
                   'selimut fleece', 'karpet bulu', 'gantungan kunci', 'celengan digital'],
        'background': ['kitchen counter top view', 'wooden table home product',
                       'clean table surface home', 'kitchen shelf products display',
                       'cozy home table setup'],
        'video_bg': ['kitchen interior home aesthetic', 'cozy home decor cinematic',
                     'morning light room interior', 'house tour modern'],
        'music_mood': 'tropical',
        'hashtags': ['#home', '#homeliving', '#rumah', '#dapur', '#shopee',
                     '#affiliate', '#recommended', '#viral'],
        'accent_color': (255, 152, 0),    # Orange
    },
    'wellness': {
        'scrape': ['matras yoga', 'resistance band', 'botol minum 2L', 'shaker protein',
                   'alat pijat', 'essential oil', 'diffuser humidifier', 'termos stainless',
                   'timbangan badan', 'foam roller', 'suplemen vitamin', 'masker olahraga',
                   'knee support', 'jump rope', 'hand grip', 'ankle weight',
                   'dumbbell set', 'pull up bar', 'yoga block', 'gym gloves',
                   'waist trainer', 'ab roller', 'sports bra', 'legging sport',
                   'kaos olahraga dryfit', 'headband sport', 'cooling towel',
                   'tumbler infuser', 'pedometer', 'wrist band sport', 'kinesiology tape'],
        'background': ['yoga mat flatlay equipment', 'fitness products on wooden floor',
                       'healthy lifestyle table setup', 'gym equipment flatlay',
                       'wellness products display surface'],
        'video_bg': ['nature yoga zen meditation', 'sunrise landscape cinematic',
                     'water flowing peaceful', 'green leaves nature abstract'],
        'music_mood': 'upbeat',
        'hashtags': ['#health', '#wellness', '#fitness', '#healthy', '#shopee',
                     '#affiliate', '#recommended', '#viral'],
        'accent_color': (76, 175, 80),    # Green
    },
}

# ═══════════════════════════════════════════════════════════════════
#  COPYWRITING BANK PER CATEGORY (15 variants each)
#  Used by: variation engine for hook/body/CTA text
# ═══════════════════════════════════════════════════════════════════
COPYWRITING_BANK = {
    'fashion': {
        'hooks': [
            "Style kamu upgrade INSTANT!", "Outfit ini lagi viral banget!",
            "Gaya kekinian harga ramah!", "Yang ini wajib masuk wishlist!",
            "Anti ribet, auto stylish!", "Cocok buat OOTD kamu!",
            "Fashion find terbaik bulan ini!", "Ini sih game changer!",
            "Budget friendly tapi kelihatan mahal!", "Paling dicari minggu ini!",
            "Semua orang nanya ini beli dimana!", "Tampilanmu auto beda!",
            "Fashion hack yang harus kamu tau!", "Under 100rb tapi premium!",
            "Outfit staple yang wajib punya!",
        ],
        'cta': [
            "Buruan checkout sebelum kehabisan!", "Klik link di deskripsi sekarang!",
            "Grab yours sebelum sold out!", "Link Shopee di deskripsi ya!",
            "Order sekarang, besok sampai!", "Cek deskripsi buat link-nya!",
        ],
    },
    'gadget': {
        'hooks': [
            "Tech find yang bikin WOW!", "Gadget murah kualitas sultan!",
            "Ini tools wajib punya!", "Upgrade setup kamu sekarang!",
            "Reviewed: Worth it atau SKIP?", "Gadget viral yang ternyata berguna!",
            "Paling dicari tech enthusiast!", "Harga segini dapet fitur segini??",
            "Setup upgrade under 100rb!", "Hidden gem di Shopee!",
            "Gadget ini bikin hidup lebih gampang!", "Unboxing + honest review!",
            "Best buy gadget bulan ini!", "Budget tech yang mengejutkan!",
            "Ini yang kamu butuhkan tapi belum tau!",
        ],
        'cta': [
            "Link pembelian di deskripsi!", "Cek harga di Shopee sekarang!",
            "Grab deal-nya sebelum naik harga!", "Link di deskripsi, buruan!",
            "Order via link affiliate di deskripsi!", "Klik link Shopee di bawah!",
        ],
    },
    'beauty': {
        'hooks': [
            "Skincare game changer!", "Kulit glowing dalam 7 hari!",
            "Beauty find yang bikin kaget!", "Produk viral TikTok: worth it?",
            "Rahasia kulit mulus ala Korea!", "Review jujur produk ini!",
            "Skincare budget tapi hasilnya WOW!", "Ingredients bagus harga bersahabat!",
            "Ini yang bikin kulit makin bagus!", "Dermatologist approved ternyata!",
            "Produk lokal yang underrated!", "Morning routine must-have!",
            "Nighttime skincare essential!", "Before-after pakai produk ini!",
            "Anti aging terbaik di kelasnya!",
        ],
        'cta': [
            "Link Shopee di deskripsi!", "Coba sekarang, kulitmu akan berterima kasih!",
            "Klik link di bawah buat beli!", "Harga promo terbatas!",
            "Order sekarang sebelum harga naik!", "Link pembelian ada di deskripsi!",
        ],
    },
    'home': {
        'hooks': [
            "Rumah auto rapi dengan ini!", "Solusi practical buat rumahmu!",
            "Bikin dapur makin aesthetic!", "Alat rumah anti ribet!",
            "Home hack yang wajib dicoba!", "Bikin rumah makin betah!",
            "Organizer terbaik bulan ini!", "Budget deco tapi kelihatan mahal!",
            "Solusi storage yang cerdas!", "Bikin rumah sekecil apapun terasa luas!",
            "Kitchen tools yang membantu banget!", "Cleaning hack super praktis!",
            "Interior upgrade tanpa mahal!", "Rumah bersih tanpa capek!",
            "Alat ajaib yang sering di-skip!",
        ],
        'cta': [
            "Link Shopee di deskripsi!", "Order sekarang buat rumah lebih rapi!",
            "Cek harganya di link bawah!", "Promo terbatas, buruan!",
            "Link ada di deskripsi ya!", "Beli sekarang, rumah auto keren!",
        ],
    },
    'wellness': {
        'hooks': [
            "Investasi kesehatan terbaik!", "Fitness tool yang bikin rajin!",
            "Healthy lifestyle jadi gampang!", "Alat workout wajib punya!",
            "Self-care essential bulan ini!", "Upgrade kesehatan mulai dari sini!",
            "Reviewed: Beneran works!", "Bikin olahraga makin semangat!",
            "Wellness product yang viral!", "Mulai hidup sehat dari sekarang!",
            "Body care yang direkomendasiin!", "Morning routine game changer!",
            "Recovery tool terbaik!", "Self-care tanpa ribet!",
            "Investasi tubuh yang worth it!",
        ],
        'cta': [
            "Link Shopee di deskripsi!", "Mulai sekarang, tubuhmu nanti berterima kasih!",
            "Cek link di bawah ya!", "Harga promo terbatas!",
            "Order via link di deskripsi!", "Start your journey, link di bawah!",
        ],
    },
}

# ═══════════════════════════════════════════════════════════════════
#  PUBLIC API FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def get_category(account_id):
    """Get category string for an account. Works for yt_*, tt_*, fb_*."""
    if account_id in YOUTUBE_CATEGORIES:
        return YOUTUBE_CATEGORIES[account_id]['category']
    if account_id == TIKTOK_ACCOUNT['account_id']:
        return TIKTOK_ACCOUNT['category']
    if account_id == FACEBOOK_ACCOUNT['account_id']:
        return FACEBOOK_ACCOUNT['category']
    return 'home'  # fallback


def get_label(account_id):
    """Get human-readable category label for an account."""
    if account_id in YOUTUBE_CATEGORIES:
        return YOUTUBE_CATEGORIES[account_id]['label']
    if account_id == TIKTOK_ACCOUNT['account_id']:
        return TIKTOK_ACCOUNT['label']
    if account_id == FACEBOOK_ACCOUNT['account_id']:
        return FACEBOOK_ACCOUNT['label']
    return 'Home & Living'


def get_channel_name(account_id):
    """Get YouTube channel name for an account."""
    if account_id in YOUTUBE_CATEGORIES:
        return YOUTUBE_CATEGORIES[account_id]['channel']
    return account_id


def get_keywords(category, keyword_type='scrape'):
    """Get keywords for a category. Types: scrape, background, hashtags."""
    cat = CATEGORY_KEYWORDS.get(category, CATEGORY_KEYWORDS['home'])
    return cat.get(keyword_type, [])


def get_accent_color(category):
    """Get accent color (R,G,B) for a category."""
    cat = CATEGORY_KEYWORDS.get(category, CATEGORY_KEYWORDS['home'])
    return cat.get('accent_color', (255, 152, 0))


def get_music_mood(category):
    """Get music mood string for a category."""
    cat = CATEGORY_KEYWORDS.get(category, CATEGORY_KEYWORDS['home'])
    return cat.get('music_mood', 'upbeat')


def get_scrape_keywords(category):
    """Get Shopee scrape keywords for a category."""
    return get_keywords(category, 'scrape')


def get_background_keywords(category):
    """Get background search keywords for a category."""
    return get_keywords(category, 'background')


def get_video_keywords(category):
    """Get video background search keywords for Pexels Video API."""
    return get_keywords(category, 'video_bg')


def get_hashtags(category):
    """Get hashtag list for a category."""
    return get_keywords(category, 'hashtags')


def get_copywriting(category, copy_type='hooks'):
    """Get copywriting bank for a category. Types: hooks, cta."""
    cat = COPYWRITING_BANK.get(category, COPYWRITING_BANK['home'])
    return cat.get(copy_type, [])


def get_accounts_for_platform(platform):
    """Get list of account_ids for a platform: youtube, tiktok, facebook."""
    if platform == 'youtube':
        return list(YOUTUBE_CATEGORIES.keys())
    elif platform == 'tiktok':
        return [TIKTOK_ACCOUNT['account_id']]
    elif platform == 'facebook':
        return [FACEBOOK_ACCOUNT['account_id']]
    return []


def get_all_categories():
    """Get list of all unique categories."""
    return list(CATEGORY_KEYWORDS.keys())


def get_color_grading(account_id):
    """Get color grading preset for an account from category_config.json."""
    import os, json
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'category_config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        acct_map = {
            'yt_1': 'youtube_akun_1', 'yt_2': 'youtube_akun_2',
            'yt_3': 'youtube_akun_3', 'yt_4': 'youtube_akun_4',
            'yt_5': 'youtube_akun_5', 'tt_1': 'tiktok', 'fb_1': 'facebook',
        }
        key = acct_map.get(account_id, '')
        if key in cfg:
            return cfg[key].get('color_grading', 'clean_bright')
    # Fallback mapping
    cat = get_category(account_id)
    fallback = {
        'fashion': 'warm_vibrant', 'gadget': 'cool_dark_premium',
        'beauty': 'soft_pastel', 'home': 'clean_bright',
        'wellness': 'energetic_vivid',
    }
    return fallback.get(cat, 'clean_bright')


def get_hf_api_key(account_id):
    """Get dedicated Hugging Face API key for an account."""
    import os, json
    hf_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'hf_config.json')
    if os.path.exists(hf_path):
        with open(hf_path, 'r') as f:
            mapping = json.load(f)
        acct_map = {
            'yt_1': 'youtube_akun_1', 'yt_2': 'youtube_akun_2',
            'yt_3': 'youtube_akun_3', 'yt_4': 'youtube_akun_4',
            'yt_5': 'youtube_akun_5', 'tt_1': 'tiktok', 'fb_1': 'facebook',
        }
        key = acct_map.get(account_id, 'youtube_akun_1')
        env_var = mapping.get(key, 'HF_API_KEY_1')
        return os.environ.get(env_var, '')
    return os.environ.get('HF_API_KEY_1', '')


def get_style_copy(account_id):
    """Get copywriting style for an account from category_config.json."""
    import os, json
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'category_config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        acct_map = {
            'yt_1': 'youtube_akun_1', 'yt_2': 'youtube_akun_2',
            'yt_3': 'youtube_akun_3', 'yt_4': 'youtube_akun_4',
            'yt_5': 'youtube_akun_5', 'tt_1': 'tiktok', 'fb_1': 'facebook',
        }
        key = acct_map.get(account_id, '')
        if key in cfg:
            return cfg[key].get('style_copy', 'practical_problem_solution')
    return 'practical_problem_solution'


def get_account_info(account_id):
    """Get full info dict for an account."""
    if account_id in YOUTUBE_CATEGORIES:
        info = YOUTUBE_CATEGORIES[account_id].copy()
        info['platform'] = 'youtube'
        info['account_id'] = account_id
        return info
    if account_id == TIKTOK_ACCOUNT['account_id']:
        info = TIKTOK_ACCOUNT.copy()
        info['platform'] = 'tiktok'
        return info
    if account_id == FACEBOOK_ACCOUNT['account_id']:
        info = FACEBOOK_ACCOUNT.copy()
        info['platform'] = 'facebook'
        return info
    return {'account_id': account_id, 'category': 'home', 'platform': 'unknown'}


# ═══════════════════════════════════════════════════════════════════
#  SCHEDULE CONFIG (used by batch_manager + scheduler)
# ═══════════════════════════════════════════════════════════════════
SCHEDULE = {
    'pagi':  {'type': 'long',  'time_range': ('06:30', '07:30'), 'label': 'Video Panjang'},
    'siang': {'type': 'short', 'time_range': ('11:30', '12:30'), 'label': 'Shorts'},
    'sore':  {'type': 'long',  'time_range': ('15:30', '16:30'), 'label': 'Video Panjang'},
    'malam': {'type': 'short', 'time_range': ('19:30', '20:30'), 'label': 'Shorts'},
}

# ═══════════════════════════════════════════════════════════════════
#  VIDEO DURATION CONFIG (used by video generators)
# ═══════════════════════════════════════════════════════════════════
VIDEO_DURATION = {
    'yt_long':  {'min': 60, 'max': 80, 'label': 'YouTube Long-form'},
    'yt_short': {'min': 45, 'max': 50,  'label': 'YouTube Shorts'},
    'tiktok':   {'min': 25, 'max': 30,  'label': 'TikTok'},
    'facebook': {'min': 50, 'max': 60,  'label': 'Facebook'},
}


def get_random_time(slot, rng=None):
    """Get a random time within the slot's time range."""
    import random
    _rng = rng or random
    sched = SCHEDULE.get(slot)
    if not sched:
        return '08:00'
    start_h, start_m = map(int, sched['time_range'][0].split(':'))
    end_h, end_m = map(int, sched['time_range'][1].split(':'))
    total_start = start_h * 60 + start_m
    total_end = end_h * 60 + end_m
    rand_min = _rng.randint(total_start, total_end)
    return f"{rand_min // 60:02d}:{rand_min % 60:02d}"


def get_video_type(slot):
    """Get video type for a slot: 'long' or 'short'."""
    sched = SCHEDULE.get(slot, {})
    return sched.get('type', 'short')


# ═══════════════════════════════════════════════════════════════════
#  CLI — Test / print all mappings
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("═══ Category Router ═══\n")

    print("YouTube Accounts:")
    for acct in get_accounts_for_platform('youtube'):
        info = get_account_info(acct)
        cat = info['category']
        print(f"  {acct} → {info['label']} ({info['channel']})")
        print(f"         mood={get_music_mood(cat)} color={get_accent_color(cat)}")

    print(f"\nTikTok:   {TIKTOK_ACCOUNT['account_id']} → {TIKTOK_ACCOUNT['label']}")
    print(f"Facebook: {FACEBOOK_ACCOUNT['account_id']} → {FACEBOOK_ACCOUNT['label']}")

    print("\nSchedule:")
    for slot, sched in SCHEDULE.items():
        print(f"  {slot}: {sched['type']} ({sched['time_range'][0]}-{sched['time_range'][1]} WIB)")

    print("\nScrape Keywords:")
    for cat in get_all_categories():
        kw = get_scrape_keywords(cat)
        print(f"  {cat}: {', '.join(kw[:5])}...")

    print("\nCopywriting (hooks sample):")
    for cat in get_all_categories():
        hooks = get_copywriting(cat, 'hooks')
        print(f"  {cat}: \"{hooks[0]}\"")
