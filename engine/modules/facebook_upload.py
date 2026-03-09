"""
facebook_upload.py
Upload video ke Facebook Fanpage via Graph API.
Auto-delete setelah upload berhasil.

Setup:
  1. Buat Facebook App di developers.facebook.com
  2. Dapatkan Page Access Token (long-lived)
  3. Simpan di engine/config/fb_config.json:
     {
       "page_id": "YOUR_PAGE_ID",
       "access_token": "YOUR_LONG_LIVED_PAGE_ACCESS_TOKEN"
     }

Cara dapat long-lived token:
  - Graph API Explorer → pilih Page → generate token
  - Extend token: GET /oauth/access_token?grant_type=fb_exchange_token&...
  - Page token dari long-lived user token: GET /{page-id}?fields=access_token
"""
import os
import sys
import json
import requests

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
FB_CONFIG = os.path.join(CONFIG_DIR, 'fb_config.json')


def load_fb_config():
    """Load Facebook Page credentials."""
    if not os.path.exists(FB_CONFIG):
        return None
    with open(FB_CONFIG, 'r') as f:
        return json.load(f)


def upload_to_facebook(filepath, title, description, page_id, access_token):
    """Upload video to Facebook Page via Graph API."""
    url = f"https://graph.facebook.com/v19.0/{page_id}/videos"

    with open(filepath, 'rb') as video_file:
        payload = {
            'title': title[:100],
            'description': description,
            'access_token': access_token,
        }
        files = {
            'source': (os.path.basename(filepath), video_file, 'video/mp4')
        }

        print(f"   Uploading to Facebook Page...")
        response = requests.post(url, data=payload, files=files)

    if response.status_code == 200:
        result = response.json()
        video_id = result.get('id', 'unknown')
        print(f"   [OK] Uploaded! Video ID: {video_id}")
        print(f"   URL: https://facebook.com/{video_id}")
        return video_id
    else:
        error = response.json().get('error', {}).get('message', response.text)
        print(f"   [FAIL] Upload error: {error}")
        return None


def upload_facebook(video_dir, metadata_path):
    """Upload all Facebook videos."""
    print("=== Facebook Fanpage Upload ===")

    fb_dir = os.path.join(video_dir, "fb")
    if not os.path.exists(fb_dir):
        print("No FB output directory found. Skipping upload.")
        return

    # Match all FB videos: both Long (_fb.mp4) and Short (_fb_short.mp4)
    videos = sorted([f for f in os.listdir(fb_dir)
                     if f.endswith('.mp4') and '_fb' in f])
    if not videos:
        print("No Facebook videos to upload.")
        return

    # Load FB credentials
    fb_config = load_fb_config()
    is_real = fb_config is not None

    if is_real:
        page_id = fb_config.get('page_id', '')
        access_token = fb_config.get('access_token', '')
        print(f"[OK] Facebook API configured! Page ID: {page_id[:10]}...")
    else:
        print("[INFO] No Facebook credentials. Running SIMULATION mode.")
        print("  To enable real uploads:")
        print("  1. Create engine/config/fb_config.json with:")
        print('     {"page_id": "YOUR_ID", "access_token": "YOUR_TOKEN"}')
        page_id = ''
        access_token = ''

    # Load metadata for description
    yt_metadata = {}
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r', encoding='utf-8') as f:
            meta_list = json.load(f)
            for m in meta_list:
                # Use first entry's description as base for FB
                if 'description' in m:
                    yt_metadata = m
                    break

    uploaded = []
    for v in videos:
        path = os.path.join(fb_dir, v)
        # Extract product name from filename
        parts = v.replace('.mp4', '').split('_')
        produk_id = parts[1] if len(parts) > 1 else 'unknown'

        title = yt_metadata.get('title', f"Review {produk_id}").replace('#shorts', '#reels')
        desc = yt_metadata.get('description', f"Review produk {produk_id}")
        # Replace YT-specific text with FB
        desc = desc.replace('link di deskripsi', 'link di komentar')
        desc = desc.replace('#Shorts', '#Reels').replace('#shorts', '#reels')

        print(f"\n>> Uploading to Facebook:")
        print(f"   File: {v}")
        print(f"   Title: {title}")

        if is_real:
            video_id = upload_to_facebook(path, title, desc, page_id, access_token)
            if video_id:
                uploaded.append(path)
        else:
            print(f"   [OK] Upload SUCCESS (simulated)")
            uploaded.append(path)

    # Write uploaded list for cleanup
    uploaded_list_path = os.path.join(fb_dir, "_uploaded.json")
    with open(uploaded_list_path, 'w') as f:
        json.dump(uploaded, f, indent=2)

    print(f"\n=== Facebook upload complete: {len(uploaded)} videos ===")
    print(f"Uploaded list saved to {uploaded_list_path}")


if __name__ == "__main__":
    upload_facebook(
        "engine/output",
        "engine/state/yt_metadata.json"
    )
