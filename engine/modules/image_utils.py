"""
image_utils.py
Shared image utilities for all video generators.

- auto_trim_whitespace: remove white borders from Shopee product images
- load_and_prepare_product: load, trim, scale product image for compositing
"""
import os
import numpy as np
from PIL import Image


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
