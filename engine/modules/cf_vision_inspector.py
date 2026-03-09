"""
cf_vision_inspector.py
AI-powered image quality inspection using Cloudflare Workers AI (LLaVA).

Inspects product images for:
  - Product clarity: is the product clearly visible?
  - Text clutter: is there overlaid text/watermarks blocking the product?
  - Background cleanliness: is the background distracting?
  - Overall composition: suitable for video frame?

Returns quality score (0-100) and recommendations.
Integrates with download_images.py to select the BEST image.
"""

import os
import json
import base64
import requests
from PIL import Image
from io import BytesIO

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
CF_MODEL = '@cf/llava-hf/llava-1.5-7b-hf'


def _get_cf_credentials():
    """Get CF credentials — tries any available key."""
    for i in range(1, 8):
        acc_id = os.environ.get(f'CF_ACCOUNT_ID_{i}', '')
        api_key = os.environ.get(f'CF_API_KEY_{i}', '')
        if acc_id and api_key:
            return acc_id, api_key
    acc_id = os.environ.get('CF_ACCOUNT_ID', '')
    api_key = os.environ.get('CF_API_KEY', '')
    if acc_id and api_key:
        return acc_id, api_key
    return None, None


def inspect_image(img_path, category='home'):
    """Inspect a product image using AI vision model.
    
    Args:
        img_path: path to image file
        category: product category for context
    
    Returns:
        dict with:
          - score: 0-100 (higher = better for video)
          - issues: list of detected problems
          - recommendation: 'use', 'enhance', or 'skip'
    """
    account_id, api_key = _get_cf_credentials()
    
    if not api_key or not account_id:
        print(f"    [VISION] No CF credentials, using pixel analysis")
        return _fallback_inspect(img_path)
    
    try:
        # Load and resize image for API (max 512x512 to save bandwidth)
        img = Image.open(img_path).convert('RGB')
        img_small = img.copy()
        img_small.thumbnail((512, 512), Image.LANCZOS)
        
        # Convert to base64
        buffer = BytesIO()
        img_small.save(buffer, format='PNG')
        img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        prompt = """Analyze this product image for e-commerce video use. Rate on these criteria:
1. Product visibility: Is the product clearly visible and prominent? (0-10)
2. Text/clutter: Is there overlaid text, watermarks, or busy graphics? (0-10, 10=no text/clutter)
3. Background: Is the background clean and non-distracting? (0-10, 10=clean)
4. Composition: Is it suitable for a 9:16 vertical video frame? (0-10)

Respond ONLY in this JSON format:
{"product_visible": 8, "no_clutter": 7, "clean_bg": 6, "composition": 7, "issues": ["brief issue 1"], "overall": 70}"""

        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CF_MODEL}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "image": img_b64,
            "max_tokens": 200,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=30)

        if resp.status_code != 200:
            print(f"    [VISION] HTTP {resp.status_code}")
            return _fallback_inspect(img_path)

        data = resp.json()
        result_text = data.get('result', {}).get('response', '')
        
        # Parse JSON response
        result = _parse_vision_response(result_text)
        if result:
            score = result.get('overall', 50)
            issues = result.get('issues', [])
            
            if score >= 70:
                recommendation = 'use'
            elif score >= 40:
                recommendation = 'enhance'
            else:
                recommendation = 'skip'
            
            print(f"    [VISION] Score={score}, rec={recommendation}")
            return {
                'score': score,
                'issues': issues,
                'recommendation': recommendation,
                'details': result,
            }

        return _fallback_inspect(img_path)

    except Exception as e:
        print(f"    [VISION] Error: {e}")
        return _fallback_inspect(img_path)


def _parse_vision_response(text):
    """Extract JSON from vision model response."""
    try:
        return json.loads(text)
    except Exception:
        pass
    
    import re
    json_match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except Exception:
            pass
    
    return None


def _fallback_inspect(img_path):
    """Pixel-based fallback inspection when AI is unavailable."""
    try:
        import numpy as np
        img = Image.open(img_path).convert('RGB')
        data = np.array(img)
        h, w = data.shape[:2]
        
        score = 50  # Start neutral
        issues = []
        
        # Check brightness
        brightness = data.mean()
        if brightness < 80:
            score -= 15
            issues.append("too dark")
        elif brightness > 240:
            score -= 5
            issues.append("overexposed")
        else:
            score += 10
        
        # Check edge complexity (text indicator)
        gray = data.mean(axis=2).astype(np.uint8)
        edges = np.abs(gray[1:, :].astype(int) - gray[:-1, :].astype(int))
        edge_density = (edges > 50).sum() / (h * w)
        if edge_density > 0.15:
            score -= 20
            issues.append("high text/clutter density")
        elif edge_density < 0.05:
            score += 15
        
        # Check border uniformity (clean background)
        border = 15
        border_std = np.std(data[:border, :, :])
        if border_std < 20:
            score += 15
        elif border_std > 60:
            score -= 10
            issues.append("busy edges")
        
        score = max(0, min(100, score))
        
        if score >= 65:
            recommendation = 'use'
        elif score >= 35:
            recommendation = 'enhance'
        else:
            recommendation = 'skip'
        
        return {
            'score': score,
            'issues': issues,
            'recommendation': recommendation,
            'details': {'method': 'pixel_analysis'},
        }
    
    except Exception:
        return {'score': 50, 'issues': [], 'recommendation': 'enhance', 'details': {}}


def inspect_and_select_best(image_paths, category='home'):
    """Inspect multiple images and return the best one.
    
    Args:
        image_paths: list of image file paths
        category: product category
    
    Returns:
        (best_path, inspection_result) or (None, None)
    """
    if not image_paths:
        return None, None
    
    best_path = None
    best_score = -1
    best_result = None
    
    for path in image_paths:
        if not os.path.exists(path):
            continue
        
        result = inspect_image(path, category)
        if result['score'] > best_score:
            best_score = result['score']
            best_path = path
            best_result = result
    
    if best_path:
        print(f"    [VISION] Best image: {os.path.basename(best_path)} (score={best_score})")
    
    return best_path, best_result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True, help='Image to inspect')
    parser.add_argument('--category', default='home')
    args = parser.parse_args()
    
    result = inspect_image(args.image, args.category)
    print(json.dumps(result, indent=2))
