"""
image_utils.py
Shared image & product utilities for all video generators.

- auto_trim_whitespace: remove white borders from Shopee product images
- clean_product_name: shorten long Shopee names to descriptive part only
"""
import os
import re
import numpy as np
from PIL import Image


def clean_product_name(nama):
    """Shorten long Shopee product names to the descriptive part.
    
    Shopee names follow pattern:
      "Brand - Generic Category / Specific Name / Extra Details / More..."
    
    We want just "Specific Name" — the part after the first "/" separator.
    If no separator, take the first meaningful segment.
    
    Examples:
      "Puswall - Stiker Dinding / Wallsticker Motive Lamp / Dekorasi..."
        → "Wallsticker Motive Lamp"
      "PROMO Tas Selempang Wanita Korean Style"
        → "Tas Selempang Wanita Korean Style"
      "Simple Product Name"
        → "Simple Product Name"
    """
    if not nama or len(nama) < 5:
        return nama
    
    # Split by "/" first (most common Shopee separator)
    if '/' in nama:
        parts = [p.strip() for p in nama.split('/')]
        # Take second segment (after first /) — usually the descriptive name
        # But skip if it's too short (< 3 words)
        if len(parts) > 1 and len(parts[1].split()) >= 2:
            nama = parts[1]
        elif len(parts) > 0:
            # Fallback: take first part if second is too short
            nama = parts[0]
    
    # If still has " - " separator (e.g. "Brand - Product Name"), take after dash
    if ' - ' in nama:
        parts = nama.split(' - ', 1)
        # Take the longer part (usually the product description)
        if len(parts[1]) > len(parts[0]):
            nama = parts[1]
        else:
            nama = parts[0]
    
    # Remove common Shopee noise prefixes
    noise = ['PROMO', 'SALE', 'DISKON', 'HOT', 'NEW', 'BEST SELLER',
             'TERMURAH', 'TERLARIS', 'COD', 'GRATIS ONGKIR', 'FREE ONGKIR']
    upper_nama = nama.upper()
    for n in noise:
        if upper_nama.startswith(n + ' '):
            nama = nama[len(n):].strip()
            upper_nama = nama.upper()
            # Strip leading punctuation after removing noise
            nama = nama.lstrip('!-– ').strip()
    
    # Truncate to max ~50 chars at word boundary
    if len(nama) > 50:
        words = nama[:55].split()
        nama = ' '.join(words[:-1]) if len(words) > 1 else nama[:50]
    
    return nama.strip()



def auto_trim_whitespace(product_img, is_transparent=False, threshold=235):
    """Remove white/light borders from product images.
    
    Many Shopee product images have white padding/margins that look ugly
    when composited onto premium gradient backgrounds.
    
    Args:
        product_img: PIL Image (RGB or RGBA)
        is_transparent: True if image has alpha channel
        threshold: pixels brighter than this are considered "white border"
    
    Returns: cropped PIL Image (same mode)
    """
    try:
        if is_transparent:
            # For RGBA: crop to alpha bounding box (non-transparent area)
            alpha = product_img.split()[3]
            bbox = alpha.getbbox()
        else:
            # For RGB: detect near-white borders and trim them
            data = np.array(product_img)
            # A pixel is "content" if ANY channel is below threshold
            content_mask = np.any(data < threshold, axis=2)
            rows = np.any(content_mask, axis=1)
            cols = np.any(content_mask, axis=0)
            if rows.any() and cols.any():
                y1, y2 = np.where(rows)[0][[0, -1]]
                x1, x2 = np.where(cols)[0][[0, -1]]
                # Add 2% padding so product isn't flush against edges
                ph, pw = data.shape[:2]
                pad_x = max(5, int(pw * 0.02))
                pad_y = max(5, int(ph * 0.02))
                bbox = (max(0, x1 - pad_x), max(0, y1 - pad_y),
                        min(pw, x2 + pad_x + 1), min(ph, y2 + pad_y + 1))
            else:
                bbox = None

        if bbox:
            old_w, old_h = product_img.size
            product_img = product_img.crop(bbox)
            new_w, new_h = product_img.size
            # Only log if we actually trimmed something meaningful
            trimmed_pixels = (old_w * old_h) - (new_w * new_h)
            if trimmed_pixels > 1000:
                print(f"    [TRIM] White borders removed: {old_w}x{old_h} → {new_w}x{new_h}")
    except Exception:
        pass  # If trim fails, return original image unchanged
    
    return product_img
