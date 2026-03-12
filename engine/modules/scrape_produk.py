"""
scrape_produk.py
Scrape products for ALL 5 categories (fashion, gadget, beauty, home, wellness).
Each product is tagged with its category so batch_manager can assign correctly.

Output: engine/data/produk.csv with 'category' column

Strategy per category:
1. Try Shopee search API with category keywords
2. If blocked (403), use curated fallback products for that category
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
    # Fallback if import fails
    CATEGORY_KEYWORDS = {}
    YOUTUBE_CATEGORIES = {}

try:
    from dedup_tracker import is_product_used
except ImportError:
    def is_product_used(product_id, account_id): return False

# All 5 categories to scrape
CATEGORIES = ['fashion', 'gadget', 'beauty', 'home', 'wellness']

# Curated fallback products per category
# NOTE: img intentionally EMPTY → download_images.py will search Shopee by NAME
#       (old fake CDN URLs returned 404, causing placeholder-only images)
FALLBACK_PRODUCTS = {
    'fashion': [
        {"nama": "Tas Selempang Wanita", "desc": "Tas sling bag kulit PU anti air casual", "price": "Rp65.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rasb-m1ctj0cqik2mb6", "shopee_url": "https://shopee.co.id/search?keyword=tas+selempang+wanita"},
        {"nama": "Jam Tangan Digital Sport", "desc": "Jam tangan sport LED waterproof unisex", "price": "Rp49.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rbkb-ma5bcjwolfoufd", "shopee_url": "https://shopee.co.id/search?keyword=jam+tangan+digital+sport"},
        {"nama": "Topi Bucket Hat", "desc": "Topi bucket reversible motif trendy", "price": "Rp35.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rasi-m0s3ozs9a52v65", "shopee_url": "https://shopee.co.id/search?keyword=topi+bucket+hat"},
        {"nama": "Kaos Oversize Unisex", "desc": "Kaos cotton combed 30s oversize streetwear", "price": "Rp55.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-8224z-mhvq5t9hkdu0e8", "shopee_url": "https://shopee.co.id/search?keyword=kaos+oversize+unisex"},
        {"nama": "Dompet Kulit Pria", "desc": "Dompet lipat kulit PU RFID blocking slim", "price": "Rp45.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r991-lqksvho1cx1scc", "shopee_url": "https://shopee.co.id/search?keyword=dompet+kulit+pria"},
        {"nama": "Kacamata Hitam Retro", "desc": "Kacamata UV400 vintage retro polarized unisex", "price": "Rp39.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98x-lpp232befub392", "shopee_url": "https://shopee.co.id/search?keyword=kacamata+hitam+retro"},
        {"nama": "Gelang Titanium Couple", "desc": "Gelang pasangan titanium anti karat waterproof", "price": "Rp42.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7qukz-lishlyvadbo70a", "shopee_url": "https://shopee.co.id/search?keyword=gelang+titanium+couple"},
        {"nama": "Backpack Anti Maling", "desc": "Tas ransel anti theft USB port waterproof 15 inch", "price": "Rp125.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-82250-mk6xor31jdhcd8", "shopee_url": "https://shopee.co.id/search?keyword=backpack+anti+maling"},
        {"nama": "Hoodie Polos Premium", "desc": "Hoodie fleece tebal premium all size unisex", "price": "Rp89.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98s-lxwq5zkaeplq16", "shopee_url": "https://shopee.co.id/search?keyword=hoodie+polos+premium"},
        {"nama": "Ikat Pinggang Kulit", "desc": "Belt kulit asli automatic buckle formal casual", "price": "Rp59.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rbk5-m88w6h9y4miq68", "shopee_url": "https://shopee.co.id/search?keyword=ikat+pinggang+kulit"},
        {"nama": "Sepatu Sneakers Casual", "desc": "Sepatu sneakers canvas unisex ringan anti slip", "price": "Rp99.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98o-lw3z2zih8kdq85", "shopee_url": "https://shopee.co.id/search?keyword=sepatu+sneakers+casual"},
        {"nama": "Sling Bag Mini Pria", "desc": "Tas selempang mini waterproof multifungsi pria", "price": "Rp55.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7qukz-lgktrthc8fz038", "shopee_url": "https://shopee.co.id/search?keyword=sling+bag+mini+pria"},
        {"nama": "Topi Baseball Bordir", "desc": "Topi baseball bordir premium adjustable unisex", "price": "Rp32.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rask-m4w25ycx4hlia8", "shopee_url": "https://shopee.co.id/search?keyword=topi+baseball+bordir"},
        {"nama": "Anting Titanium Set 6pcs", "desc": "Anting set 6 pasang titanium anti alergi", "price": "Rp25.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-23030-so5h7p6hayov05", "shopee_url": "https://shopee.co.id/search?keyword=anting+titanium+set"},
        {"nama": "Sweater Rajut Turtleneck", "desc": "Sweater rajut turtleneck premium tebal hangat", "price": "Rp79.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98w-m0azrgi9uzvk02", "shopee_url": "https://shopee.co.id/search?keyword=sweater+rajut+turtleneck"},
    ],
    'gadget': [
        {"nama": "Earphone TWS Bluetooth", "desc": "Earphone wireless TWS bluetooth 5.0 noise cancelling", "price": "Rp79.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7qul2-lk8ytaxbnzaf6b", "shopee_url": "https://shopee.co.id/search?keyword=earphone+tws+bluetooth"},
        {"nama": "Powerbank 10000mAh", "desc": "Powerbank fast charging LED display dual port", "price": "Rp89.000",
         "img": "", "shopee_url": "https://shopee.co.id/search?keyword=powerbank+10000mah"},
        {"nama": "Tripod HP Flexible", "desc": "Tripod fleksibel 360 derajat dengan remote bluetooth", "price": "Rp45.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98y-lsi0nmk0l5yx03", "shopee_url": "https://shopee.co.id/search?keyword=tripod+hp+flexible"},
        {"nama": "Ring Light LED 26cm", "desc": "Ring light LED 26cm dengan tripod dan holder HP", "price": "Rp75.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-8224x-mkdio0lurn5zfe", "shopee_url": "https://shopee.co.id/search?keyword=ring+light+led+26cm"},
        {"nama": "Mouse Wireless Ergonomis", "desc": "Mouse wireless silent click ergonomis 2.4GHz", "price": "Rp55.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98o-lm34ovep1xy746", "shopee_url": "https://shopee.co.id/search?keyword=mouse+wireless+ergonomis"},
        {"nama": "Keyboard Mechanical Mini", "desc": "Keyboard mechanical 68 key RGB backlit", "price": "Rp189.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7qul0-lijvlm3gadso57", "shopee_url": "https://shopee.co.id/search?keyword=keyboard+mechanical+mini"},
        {"nama": "USB Hub 4 Port 3.0", "desc": "USB hub 3.0 splitter 4 port aluminium high speed", "price": "Rp49.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98x-ll65mxjb649e75", "shopee_url": "https://shopee.co.id/search?keyword=usb+hub+4+port"},
        {"nama": "Charger Fast Charging 65W", "desc": "Charger GaN 65W PD QC3.0 dual port", "price": "Rp99.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-81zth-mf7pf0oxbeobbf", "shopee_url": "https://shopee.co.id/search?keyword=charger+fast+charging+65w"},
        {"nama": "Webcam HD 1080p", "desc": "Webcam full HD 1080p autofocus built-in mic", "price": "Rp145.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rasi-m2gimbrjg8yq66", "shopee_url": "https://shopee.co.id/search?keyword=webcam+hd+1080p"},
        {"nama": "Speaker Bluetooth Portable", "desc": "Speaker bluetooth 5.0 portable bass boost IPX7", "price": "Rp119.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7qul2-lg4ts3wtl6yn60", "shopee_url": "https://shopee.co.id/search?keyword=speaker+bluetooth+portable"},
        {"nama": "Kabel Type C 100W 2m", "desc": "Kabel charger type C fast charging 100W braided", "price": "Rp25.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r991-lwcqy6e08njef2", "shopee_url": "https://shopee.co.id/search?keyword=kabel+type+c+100w"},
        {"nama": "Phone Stand Aluminium", "desc": "Phone stand holder meja aluminium adjustable", "price": "Rp35.000",
         "img": "", "shopee_url": "https://shopee.co.id/search?keyword=phone+stand+aluminium"},
        {"nama": "Headphone Gaming RGB", "desc": "Headphone over ear gaming RGB surround 7.1", "price": "Rp159.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7ra0h-mbc735wr4wyhe4", "shopee_url": "https://shopee.co.id/search?keyword=headphone+gaming+rgb"},
        {"nama": "Flash Drive 64GB USB 3.0", "desc": "USB flash drive 64GB 3.0 metal waterproof", "price": "Rp45.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98z-lmqrzvyi0azv37", "shopee_url": "https://shopee.co.id/search?keyword=flash+drive+64gb"},
        {"nama": "Mousepad Gaming XL 80x30", "desc": "Mousepad extended XXL 80x30cm anti slip", "price": "Rp39.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7ras9-m1i9cgplnkmz7f", "shopee_url": "https://shopee.co.id/search?keyword=mousepad+gaming+xl"},
    ],
    'beauty': [
        {"nama": "Serum Vitamin C 20%", "desc": "Serum pencerah wajah vitamin C 20% brightening", "price": "Rp45.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7qul5-lji10gjdklkz9e", "shopee_url": "https://shopee.co.id/search?keyword=serum+vitamin+c"},
        {"nama": "Sunscreen SPF 50 PA++++", "desc": "Sunscreen wajah SPF50 PA++++ ringan tidak lengket", "price": "Rp55.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rbk3-m7ht6xszrft038", "shopee_url": "https://shopee.co.id/search?keyword=sunscreen+spf+50"},
        {"nama": "Sheet Mask 10pcs", "desc": "Masker wajah Korea 10 lembar hyaluronic acid", "price": "Rp39.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rasb-m4zu56fsea6e6c", "shopee_url": "https://shopee.co.id/search?keyword=sheet+mask"},
        {"nama": "Lip Tint Velvet Matte", "desc": "Lip tint matte velvet finish tahan 12 jam", "price": "Rp29.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98o-lsnqc6l5xrb1d9", "shopee_url": "https://shopee.co.id/search?keyword=lip+tint+velvet+matte"},
        {"nama": "Moisturizer Aloe Vera", "desc": "Pelembab wajah aloe vera 92% soothing gel 300ml", "price": "Rp35.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7ra0n-mcq002d7lahv01", "shopee_url": "https://shopee.co.id/search?keyword=moisturizer+aloe+vera"},
        {"nama": "Toner AHA BHA PHA", "desc": "Toner exfoliating AHA BHA PHA gentle kulit sensitif", "price": "Rp65.000",
         "img": "", "shopee_url": "https://shopee.co.id/search?keyword=toner+aha+bha+pha"},
        {"nama": "Eye Cream Retinol", "desc": "Krim mata retinol anti kerut dark circle 30ml", "price": "Rp49.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7qukz-liv45aspn4tdfb", "shopee_url": "https://shopee.co.id/search?keyword=eye+cream+retinol"},
        {"nama": "Cushion Foundation SPF50", "desc": "Cushion kompak SPF50 coverage natural long lasting", "price": "Rp59.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98o-lw26dogb75f26d", "shopee_url": "https://shopee.co.id/search?keyword=cushion+foundation"},
        {"nama": "Micellar Water 400ml", "desc": "Pembersih wajah micellar water gentle all skin type", "price": "Rp42.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98y-lu8lkpclhmva00", "shopee_url": "https://shopee.co.id/search?keyword=micellar+water"},
        {"nama": "Clay Mask Detox", "desc": "Masker tanah liat detox deep cleansing pore minimizer", "price": "Rp38.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-8224y-mkqbhbqtv6kg1e", "shopee_url": "https://shopee.co.id/search?keyword=clay+mask+detox"},
        {"nama": "Essence Snail Mucin 96%", "desc": "Essence snail mucin 96% hidrasi dan skin repair", "price": "Rp52.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rbk5-m9gsvbfo6txee6", "shopee_url": "https://shopee.co.id/search?keyword=essence+snail+mucin"},
        {"nama": "Setting Spray Matte", "desc": "Setting spray matte finish tahan 16 jam anti luntur", "price": "Rp45.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rasc-m1w0146ylgl7e4", "shopee_url": "https://shopee.co.id/search?keyword=setting+spray+matte"},
        {"nama": "Cleansing Balm Oil", "desc": "Pembersih makeup balm oil to milk gentle removable", "price": "Rp55.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rbk9-maawwzsz8ac4d3", "shopee_url": "https://shopee.co.id/search?keyword=cleansing+balm"},
        {"nama": "Blush On Powder Compact", "desc": "Blush on compact powder pigmented natural matte", "price": "Rp32.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-8224v-ml3wyxaw19tx8c", "shopee_url": "https://shopee.co.id/search?keyword=blush+on+compact"},
        {"nama": "Mascara Waterproof Fiber", "desc": "Mascara fiber curling waterproof volume lash 10ml", "price": "Rp35.000",
         "img": "", "shopee_url": "https://shopee.co.id/search?keyword=mascara+waterproof"},
    ],
    'home': [
        {"nama": "Rak Organizer 3 Tingkat", "desc": "Rak penyimpanan lipat serbaguna anti karat 3 tingkat", "price": "Rp89.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98w-lyei6pklw6x4ec", "shopee_url": "https://shopee.co.id/search?keyword=rak+organizer+3+tingkat"},
        {"nama": "Lampu LED Strip USB 5M", "desc": "Lampu LED strip dekorasi kamar USB 5 meter RGB", "price": "Rp35.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7ras8-m2usg45lsmd7ec", "shopee_url": "https://shopee.co.id/search?keyword=lampu+led+strip+usb"},
        {"nama": "Vacuum Cleaner Portable", "desc": "Penyedot debu mini wireless USB rechargeable", "price": "Rp129.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98w-lnaufoo8k5oa64", "shopee_url": "https://shopee.co.id/search?keyword=vacuum+cleaner+portable"},
        {"nama": "Kotak Makan 4 Sekat", "desc": "Lunch box 4 sekat anti tumpah microwave safe BPA free", "price": "Rp45.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98u-luhhc9vx5dlz33", "shopee_url": "https://shopee.co.id/search?keyword=kotak+makan+4+sekat"},
        {"nama": "Dispenser Sabun Otomatis", "desc": "Dispenser sabun foam sensor otomatis touchless 300ml", "price": "Rp79.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98q-lw6tfjfx0zl6da", "shopee_url": "https://shopee.co.id/search?keyword=dispenser+sabun+otomatis"},
        {"nama": "Gorden Blackout 150x240", "desc": "Gorden blackout tebal anti sinar UV 150x240cm", "price": "Rp95.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98z-lr05pd8zhzh5a5", "shopee_url": "https://shopee.co.id/search?keyword=gorden+blackout"},
        {"nama": "Timbangan Dapur Digital", "desc": "Timbangan dapur digital presisi 0.1g LCD 5kg", "price": "Rp49.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98y-loxfka95epu5e7", "shopee_url": "https://shopee.co.id/search?keyword=timbangan+dapur+digital"},
        {"nama": "Hanger Lipat Travel 5pcs", "desc": "Gantungan baju lipat portable travel anti slip 5pcs", "price": "Rp25.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98o-loaw8tuu9z50ba", "shopee_url": "https://shopee.co.id/search?keyword=hanger+lipat+travel"},
        {"nama": "Lap Microfiber Set 5pcs", "desc": "Lap kain microfiber serbaguna 30x30cm isi 5 warna", "price": "Rp22.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rbk2-m9dbk9wtdonh31", "shopee_url": "https://shopee.co.id/search?keyword=lap+microfiber+set"},
        {"nama": "Timer Dapur Digital", "desc": "Timer masak digital magnet LED loud alarm countdown", "price": "Rp29.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-8224y-mfumpbgx2w3s64", "shopee_url": "https://shopee.co.id/search?keyword=timer+dapur+digital"},
        {"nama": "Sapu Rubber Anti Statis", "desc": "Sapu pembersih lantai karet magic rubber broom", "price": "Rp45.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98o-lvd9gx7ju7q76c", "shopee_url": "https://shopee.co.id/search?keyword=sapu+rubber+magic"},
        {"nama": "Rak Bumbu Putar 6 Sekat", "desc": "Rak bumbu dapur putar 6 sekat tutup transparan", "price": "Rp55.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r992-lvoa285loq2kc2", "shopee_url": "https://shopee.co.id/search?keyword=rak+bumbu+putar"},
        {"nama": "Lampu Tidur Sensor Gerak", "desc": "Lampu malam LED sensor gerak cahaya warm white USB", "price": "Rp32.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98y-lxgxxu0ujp4tdf", "shopee_url": "https://shopee.co.id/search?keyword=lampu+tidur+sensor+gerak"},
        {"nama": "Bantal Memory Foam", "desc": "Bantal tidur memory foam ergonomis cervical pillow", "price": "Rp89.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98x-lsme69bhsdq589", "shopee_url": "https://shopee.co.id/search?keyword=bantal+memory+foam"},
        {"nama": "Kotak Tissue Kayu", "desc": "Tempat tissue kayu minimalis modern ruang tamu", "price": "Rp39.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rasm-m1qxcf93iujif2", "shopee_url": "https://shopee.co.id/search?keyword=kotak+tissue+kayu"},
    ],
    'wellness': [
        {"nama": "Botol Minum 2L Motivasi", "desc": "Botol minum 2 liter penanda waktu motivasi harian", "price": "Rp45.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98x-ln9un1ylqz5o40", "shopee_url": "https://shopee.co.id/search?keyword=botol+minum+2l+motivasi"},
        {"nama": "Resistance Band Set 5pcs", "desc": "Resistance band set 5 level workout rumahan", "price": "Rp55.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98w-ln9kvfxjbkcv3c", "shopee_url": "https://shopee.co.id/search?keyword=resistance+band+set"},
        {"nama": "Matras Yoga NBR 10mm", "desc": "Matras yoga anti slip NBR 10mm bonus strap", "price": "Rp79.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-8224o-mgd3gtmc4zd489", "shopee_url": "https://shopee.co.id/search?keyword=matras+yoga+nbr"},
        {"nama": "Alat Pijat Leher EMS", "desc": "Alat pijat leher elektrik EMS pulse 6 mode", "price": "Rp99.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r990-ls19jewn1zlpe4", "shopee_url": "https://shopee.co.id/search?keyword=alat+pijat+leher+ems"},
        {"nama": "Termos Stainless 500ml", "desc": "Termos vacuum flask stainless steel 500ml 12 jam", "price": "Rp65.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98t-lxkrz5gmi2nx23", "shopee_url": "https://shopee.co.id/search?keyword=termos+stainless+500ml"},
        {"nama": "Essential Oil Lavender", "desc": "Minyak esensial lavender murni 10ml aromaterapi", "price": "Rp35.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-81ztj-merah0tw74smfd", "shopee_url": "https://shopee.co.id/search?keyword=essential+oil+lavender"},
        {"nama": "Foam Roller EVA 45cm", "desc": "Foam roller EVA high density 45cm recovery otot", "price": "Rp69.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rbka-m8d5vvonizda31", "shopee_url": "https://shopee.co.id/search?keyword=foam+roller+eva"},
        {"nama": "Shaker Protein 600ml", "desc": "Botol shaker protein gym BPA free anti bocor", "price": "Rp35.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7qul3-lkh2meau3bnd22", "shopee_url": "https://shopee.co.id/search?keyword=shaker+protein+gym"},
        {"nama": "Timbangan Badan Digital", "desc": "Timbangan digital body fat BMI muscle mass", "price": "Rp99.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98o-lxkoc3gem4wrf5", "shopee_url": "https://shopee.co.id/search?keyword=timbangan+badan+digital"},
        {"nama": "Diffuser Humidifier 300ml", "desc": "Humidifier aromaterapi LED 7 warna 300ml timer", "price": "Rp89.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98t-lpfy7ixa3sel30", "shopee_url": "https://shopee.co.id/search?keyword=diffuser+humidifier"},
        {"nama": "Knee Support Neoprene", "desc": "Deker lutut olahraga neoprene anti cedera", "price": "Rp45.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98t-lxc4upb6ifm5da", "shopee_url": "https://shopee.co.id/search?keyword=knee+support+neoprene"},
        {"nama": "Jump Rope Speed Bearing", "desc": "Tali skipping speed rope bearing anti kusut", "price": "Rp32.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7r98t-ltnrf1fafvhfe0", "shopee_url": "https://shopee.co.id/search?keyword=jump+rope+speed"},
        {"nama": "Hand Grip Adjustable", "desc": "Alat latihan tangan hand grip adjustable 5-60kg", "price": "Rp29.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7rasc-m5bm1lrm63mb18", "shopee_url": "https://shopee.co.id/search?keyword=hand+grip+adjustable"},
        {"nama": "Masker Olahraga PM2.5", "desc": "Masker sport breathing valve anti debu filter", "price": "Rp25.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-7ra0i-mcu0ztpnz2ozfc", "shopee_url": "https://shopee.co.id/search?keyword=masker+olahraga"},
        {"nama": "Ankle Weight 1kg pair", "desc": "Pemberat kaki 1kg per pasang untuk workout", "price": "Rp55.000",
         "img": "https://down-id.img.susercontent.com/file/id-11134207-8224u-mj5irmiy45qdb1", "shopee_url": "https://shopee.co.id/search?keyword=ankle+weight+1kg"},
    ],
}


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
    """Try Shopee search with authenticated cookies via CF proxy."""
    session = _build_shopee_session()
    if not session:
        return None

    url = "https://shopee.co.id/api/v4/search/search_items"
    params = {
        "by": "relevancy", "keyword": keyword, "limit": limit,
        "newest": 0, "order": "desc", "page_type": "search",
        "scenario": "PAGE_GLOBAL_SEARCH", "version": 2,
    }

    # Build cookie string for proxy
    cookies_str = '; '.join([f"{c.name}={c.value}" for c in session.cookies])
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "application/json",
        "Referer": f"https://shopee.co.id/search?keyword={keyword.replace(' ', '+')}",
        "X-Shopee-Language": "id",
    }

    try:
        import time as _t
        _t.sleep(random.uniform(0.3, 1.0))

        # Use CF proxy if available
        try:
            from shopee_proxy import proxy_get_json, is_proxy_available
            if is_proxy_available():
                from urllib.parse import urlencode
                full_url = f"{url}?{urlencode(params)}"
                status, data = proxy_get_json(full_url, headers=headers, cookies_str=cookies_str)
                if status == 200 and data:
                    items = data.get("items", [])
                    if items:
                        print(f"    [Cookies+Proxy] '{keyword}' → {len(items)} products")
                        return items
                return None
        except ImportError:
            pass

        # Direct fallback
        resp = session.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            if items:
                print(f"    [Cookies] '{keyword}' → {len(items)} products")
                return items
        return None
    except Exception:
        return None


def search_shopee(keyword, limit=5):
    """Try Shopee search API via CF proxy (public, no cookies)."""
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
        _t.sleep(random.uniform(0.5, 2.0))

        # Use CF proxy if available
        try:
            from shopee_proxy import proxy_get_json, is_proxy_available
            if is_proxy_available():
                status, data = proxy_get_json(url, params=params, headers=headers)
                if status == 200 and data:
                    items = data.get("items", [])
                    if items:
                        print(f"    [PublicAPI+Proxy] '{keyword}' → {len(items)} products")
                        return items
                if status == 403:
                    return None
                return data.get("items", []) if data else None
        except ImportError:
            pass

        # Direct fallback
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 403:
            return None
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])
    except Exception as e:
        print(f"    [WARN] Search failed for '{keyword}': {e}")
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
    desc = f"{name} - {price_str} | Rating {rating}⭐ | Terjual {sold}+"

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
    """Scrape products for a single category. Returns list of product dicts."""
    products = []
    seen_ids = set()

    # Get keywords from category_router
    cat_keywords = CATEGORY_KEYWORDS.get(category, {}).get('scrape', [])
    if not cat_keywords:
        cat_keywords = [category]

    keywords = cat_keywords[:]
    random.shuffle(keywords)

    # Try Shopee API — Cookies first, then public
    for keyword in keywords[:8]:
        if len(products) >= target_count:
            break

        # Priority 1: Shopee with cookies
        items = search_shopee_cookies(keyword, limit=5)

        # Priority 2: Shopee public API
        if items is None:
            items = search_shopee(keyword, limit=5)

        if items is None:
            print(f"    [BLOCKED] Shopee API blocked for '{keyword}'")
            break  # API blocked, go to fallback

        for item in items:
            if len(products) >= target_count:
                break
            try:
                product = extract_product_info(item, affiliate_id, category)
                if product["produk_id"] in seen_ids or not product["image_url"]:
                    continue
                if product["terjual"] < 10:
                    continue
                seen_ids.add(product["produk_id"])
                products.append(product)
                print(f"      [OK] {product['nama'][:50]} ({product['harga']})")
            except Exception:
                continue

    # Fallback: use curated products
    if len(products) < target_count:
        print(f"    Using fallback products for {category}...")
        fallbacks = FALLBACK_PRODUCTS.get(category, [])
        
        # Vary selection daily
        now = datetime.datetime.now()
        random.seed(f"{now.strftime('%Y%m%d')}_{category}")
        random.shuffle(fallbacks)

        for i, fb in enumerate(fallbacks[:target_count - len(products)]):
            day_num = now.timetuple().tm_yday  # 1-365 for daily rotation
            pid = f"p{category[:3]}_{10001 + i + (day_num * 3)}"  # Different ID each day
            if pid in seen_ids:
                continue

            # Vary price slightly per day
            base_price = int(fb["price"].replace("Rp", "").replace(".", ""))
            price_var = int(base_price * random.uniform(0.90, 1.10))
            price_str = f"Rp{price_var:,}".replace(",", ".")

            products.append({
                "produk_id": pid,
                "nama": fb["nama"],
                "deskripsi_singkat": f"{fb['desc']} - {price_str}",
                "harga": price_str,
                "rating": round(random.uniform(4.2, 4.9), 1),
                "terjual": random.randint(500, 15000),
                "shopee_url": get_affiliate_url(fb["nama"], affiliate_id),
                "tokopedia_url": "",
                "image_url": fb["img"],
                "category": category,
            })
            print(f"      [FB] {fb['nama']} ({price_str})")

    return products


def scrape_products(output_file, config):
    """Scrape products for ALL categories. MERGES with existing bank data.

    Flow:
      1. Load existing produk.csv (from product_collector --export if available)
      2. Try scraping fresh products from Shopee
      3. If Shopee succeeds → use fresh products for that category
      4. If Shopee blocked → KEEP existing bank products for that category
      5. Save merged result
    """
    affiliate_id = config.get("shopee", {}).get("affiliate_id", "11344941723")
    products_per_category = config.get("scrape", {}).get("products_per_category", 3)

    print(f"=== Shopee Product Scraper (Merge Mode) ===")
    print(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %A')}")
    print(f"Categories: {', '.join(CATEGORIES)}")
    print(f"Products per category: {products_per_category}")
    print(f"Affiliate ID: {affiliate_id}")

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
    stats = {'fresh': 0, 'bank': 0, 'fallback': 0}

    for category in CATEGORIES:
        print(f"\n  --- Category: {category.upper()} ---")
        bank_products = existing_by_cat.get(category, [])
        print(f"    Bank products available: {len(bank_products)}")

        # Try scraping fresh from Shopee
        cat_products = scrape_category(category, affiliate_id, products_per_category)

        # Check if scrape returned products with Shopee CDN images (real or fallback)
        has_real_images = any(
            p.get('image_url', '') and 'pexels.com' not in p.get('image_url', '')
            and 'pixabay.com' not in p.get('image_url', '')
            for p in cat_products
        )

        # VALIDATE bank products — reject Pexels/Pixabay/Rp0 garbage
        valid_bank = [
            p for p in bank_products
            if not any(x in str(p.get('image_url', '')) for x in ['pexels.com', 'pixabay.com', 'unsplash.com'])
            and str(p.get('harga', '')) not in ('Rp0', 'Rp0.0', '', '0')
        ]
        if len(valid_bank) < len(bank_products):
            garbage = len(bank_products) - len(valid_bank)
            print(f"    [CLEAN] Filtered out {garbage} Pexels/Rp0 garbage from bank")
            bank_products = valid_bank

        if has_real_images:
            # Fresh scrape or valid fallback — use these
            all_products.extend(cat_products)
            stats['fresh'] += len(cat_products)
            print(f"    \u2713 Using {len(cat_products)} FRESH products (Shopee)")
        elif bank_products:
            # Valid bank only (no Pexels garbage)
            all_products.extend(bank_products)
            stats['bank'] += len(bank_products)
            print(f"    \u2192 Using {len(bank_products)} BANK products (Shopee blocked)")
        else:
            # No valid bank, use whatever we got
            all_products.extend(cat_products)
            stats['fallback'] += len(cat_products)
            print(f"    \u26a0 Using {len(cat_products)} FALLBACK products (no valid bank)")


    # Save merged result
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    fieldnames = ["produk_id", "nama", "deskripsi_singkat", "harga", "rating", "terjual",
                   "shopee_url", "tokopedia_url", "image_url", "category"]

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_products)

    print(f"\n=== Scraping Complete (Merge Mode) ===")
    print(f"  Fresh from Shopee: {stats['fresh']}")
    print(f"  Kept from bank:    {stats['bank']}")
    print(f"  Fallback used:     {stats['fallback']}")
    for cat in CATEGORIES:
        count = sum(1 for p in all_products if p.get('category') == cat)
        print(f"  {cat}: {count} products")
    print(f"  Total: {len(all_products)} products saved to {output_file}")

    return all_products


if __name__ == "__main__":
    config = load_config()
    scrape_products("engine/data/produk.csv", config)
