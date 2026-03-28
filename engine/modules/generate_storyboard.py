import pandas as pd
import json
import os
import sys
import random

sys.path.insert(0, os.path.dirname(__file__))
try:
    from category_router import get_copywriting, get_category
except ImportError:
    get_copywriting = None
    get_category = None

# Fallback templates (plain text, no emoji — avoids encoding issues)
HOOK_TEMPLATES = [
    "Kamu masih pakai yang biasa?",
    "STOP! Jangan scroll dulu!",
    "Wajib tau sebelum beli {nama}!",
    "Ini yang lagi viral!",
    "Review jujur {nama}!",
    "Banyak yang gak tau ini...",
    "Kenapa semua orang beli ini?",
    "Rahasia {nama} terbaik!",
    "Jangan sampai salah pilih!",
    "Cek dulu sebelum menyesal!",
]

CTA_TEMPLATES = [
    "Klik link di bio untuk beli!",
    "Cek harga spesial di link bio!",
    "Stok terbatas! Grab sekarang!",
    "Link pembelian ada di bio!",
    "Mau? Langsung klik link di bio!",
    "Jangan sampai kehabisan! Cek bio!",
    "Diskon terbatas! Link di bio!",
    "Buruan order sebelum harga naik!",
]

def generate_storyboard(produk_file, masalah_file, output_file):
    print("=== Generating Storyboard ===")
    
    if not os.path.exists(produk_file):
        print(f"Error: {produk_file} not found.")
        return
    if not os.path.exists(masalah_file):
        print(f"Error: {masalah_file} not found.")
        return
        
    produk_df = pd.read_csv(produk_file)
    
    # Load masalah — if file doesn't exist or is empty, create empty DataFrame
    if os.path.exists(masalah_file) and os.path.getsize(masalah_file) > 10:
        masalah_df = pd.read_csv(masalah_file)
    else:
        masalah_df = pd.DataFrame(columns=['produk_id', 'masalah'])
        print(f"  [INFO] masalah.csv empty/missing, will auto-generate all masalah")
    
    # LEFT merge so all products get a storyboard even without masalah
    merged = pd.merge(produk_df, masalah_df, on='produk_id', how='left')
    
    # Auto-fill missing masalah from product nama
    MASALAH_FALLBACK = [
        "Sering bingung cari {nama} yang berkualitas tapi harga terjangkau?",
        "Capek pakai {nama} murahan yang cepat rusak?",
        "Udah coba berbagai {nama} tapi belum puas?",
        "Butuh {nama} yang tahan lama dan gak mahal?",
    ]
    for idx, row in merged.iterrows():
        if pd.isna(row.get('masalah')) or str(row.get('masalah', '')).strip() == '':
            nama = str(row.get('nama', 'produk ini'))
            template = random.choice(MASALAH_FALLBACK)
            merged.at[idx, 'masalah'] = template.format(nama=nama[:30].lower())
    
    storyboards = []
    for _, row in merged.iterrows():
        nama = row['nama']
        category = row.get('category', 'fashion')
        
        # Try to get category-specific hooks/CTAs from category_router
        hook = None
        cta = None
        if get_copywriting and category:
            try:
                cat_hooks = get_copywriting(category, 'hooks')
                cat_ctas = get_copywriting(category, 'ctas')
                if cat_hooks:
                    hook = random.choice(cat_hooks)
                if cat_ctas:
                    cta = random.choice(cat_ctas)
            except Exception:
                pass
        
        # Fallback to generic templates
        if not hook:
            hook_template = random.choice(HOOK_TEMPLATES)
            hook = hook_template.format(nama=nama) if '{nama}' in hook_template else hook_template
        if not cta:
            cta = random.choice(CTA_TEMPLATES)
        
        storyboard = {
            "produk_id": row['produk_id'],
            "nama": nama,
            "category": category,
            "harga": str(row.get('harga', '')),
            "rating": float(row.get('rating', 0)),
            "terjual": int(row.get('terjual', 0)),
            "shopee_url": str(row.get('shopee_url', '')),
            "image_url": str(row.get('image_url', '')),
            "hook": hook,
            "masalah": row['masalah'],
            "solusi": f"Pakai {nama} aja!",
            "cta": cta,
            "scene_order": ["hook", "masalah", "solusi", "cta"]
        }
        storyboards.append(storyboard)
        
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        for sb in storyboards:
            f.write(json.dumps(sb, ensure_ascii=False) + '\n')
            
    print(f"Storyboard: {len(storyboards)} jobs queued.")
    for sb in storyboards:
        print(f"  {sb['produk_id']} ({sb['category']}): {sb['nama'][:40]}")

if __name__ == "__main__":
    # Try produk_valid.csv first, fallback to produk.csv if empty/missing
    produk_path = "engine/data/produk_valid.csv"
    if not os.path.exists(produk_path) or os.path.getsize(produk_path) < 50:
        produk_path = "engine/data/produk.csv"
        print(f"  [INFO] produk_valid.csv empty/missing, using {produk_path}")
    masalah_path = "engine/data/masalah.csv"
    output_path = "engine/queue/storyboard_queue.jsonl"
    generate_storyboard(produk_path, masalah_path, output_path)
