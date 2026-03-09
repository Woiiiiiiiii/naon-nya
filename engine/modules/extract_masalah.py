"""
extract_masalah.py
Extract "masalah" (pain points) for each product.
Sources (in priority order):
1. review_raw.csv (if exists) â€” real customer reviews
2. Auto-generated from product description (fallback)
"""
import pandas as pd
import os
import sys
import random


# Template masalah untuk auto-generate dari deskripsi produk
MASALAH_TEMPLATES = [
    "Sering bingung cari {nama} yang berkualitas tapi harga terjangkau?",
    "Capek pakai {nama} murahan yang cepat rusak?",
    "Masih pakai cara lama? {nama} ini solusi praktisnya!",
    "Banyak yang keluhan {nama} biasa gak awet. Ini bedanya!",
    "Udah coba berbagai {nama} tapi belum puas? Cobain yang ini!",
    "Repot banget kalau gak punya {nama} yang bener! Ini solusinya.",
    "Kesel sama {nama} yang gampang rusak? Ada solusi nih!",
    "Males ribet? {nama} ini bikin hidupmu lebih simpel!",
    "Butuh {nama} yang tahan lama dan gak mahal? Ini dia!",
    "Jangan buang uang buat {nama} abal-abal, mending yang ini!",
]


def extract_masalah(produk_file, review_file, output_file):
    """Extract masalah from reviews or auto-generate from product data."""
    print(f"Extracting masalah...")
    
    if not os.path.exists(produk_file):
        print(f"Error: {produk_file} not found.")
        return
    
    produk_df = pd.read_csv(produk_file)
    masalah_list = []
    
    # Try to use real reviews first
    if os.path.exists(review_file) and os.path.getsize(review_file) > 10:
        print(f"  Using real reviews from {review_file}")
        review_df = pd.read_csv(review_file)
        
        if 'produk_id' in review_df.columns and 'review' in review_df.columns:
            for produk_id, group in review_df.groupby('produk_id'):
                representative_review = group['review'].iloc[0]
                masalah_list.append({
                    'produk_id': produk_id,
                    'masalah': representative_review
                })
    
    # Fill in missing products with auto-generated masalah
    existing_ids = {m['produk_id'] for m in masalah_list}
    missing_products = produk_df[~produk_df['produk_id'].isin(existing_ids)]
    
    if len(missing_products) > 0:
        print(f"  Auto-generating masalah for {len(missing_products)} products...")
        
        for _, row in missing_products.iterrows():
            pid = row['produk_id']
            nama = row['nama']
            
            # Pick a random template and fill in the product name
            template = random.choice(MASALAH_TEMPLATES)
            masalah = template.format(nama=nama.lower())
            
            masalah_list.append({
                'produk_id': pid,
                'masalah': masalah
            })
    
    masalah_df = pd.DataFrame(masalah_list)
    masalah_df.to_csv(output_file, index=False)
    print(f"Masalah extraction complete. {len(masalah_df)} issues extracted.")


if __name__ == "__main__":
    produk_path = "engine/data/produk_valid.csv"
    review_path = "engine/data/review_raw.csv"
    output_path = "engine/data/masalah.csv"
    extract_masalah(produk_path, review_path, output_path)
