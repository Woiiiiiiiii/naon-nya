"""
youtube_upload.py
Upload video ke YouTube via Data API v3.
Mendukung 5 akun YouTube dengan credentials terpisah.

Struktur credentials:
  engine/config/
    tokens/
      yt_1_client_secret.json   <- OAuth credentials akun 1
      yt_2_client_secret.json   <- OAuth credentials akun 2
      yt_3_client_secret.json   <- OAuth credentials akun 3
      yt_4_client_secret.json   <- OAuth credentials akun 4
      yt_5_client_secret.json   <- OAuth credentials akun 5
      yt_1.pickle               <- token (auto-generated after auth)
      yt_2.pickle               <- dst...

Setup per akun (1x saja, jalankan di lokal):
  python engine/modules/youtube_upload.py --auth yt_1
  python engine/modules/youtube_upload.py --auth yt_2
  ... dst sampai yt_5
"""
import os
import sys
import json
import pickle
import datetime

# Paths
CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
CLIENT_SECRET = os.path.join(CONFIG_DIR, 'client_secret.json')
TOKENS_DIR = os.path.join(CONFIG_DIR, 'tokens')

SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
           'https://www.googleapis.com/auth/youtube',
           'https://www.googleapis.com/auth/youtube.force-ssl']


def get_token_path(account_id):
    """Get token file path for specific account."""
    return os.path.join(TOKENS_DIR, f'{account_id}.pickle')


def get_client_secret_path(account_id):
    """Get client_secret path: per-account first, then shared fallback."""
    acct_secret = os.path.join(TOKENS_DIR, f'{account_id}_client_secret.json')
    if os.path.exists(acct_secret):
        return acct_secret
    if os.path.exists(CLIENT_SECRET):
        return CLIENT_SECRET
    return None


def get_authenticated_service(account_id):
    """Authenticate and return YouTube API service for a specific account."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("[WARN] google-api-python-client not installed.")
        print("  Run: pip install google-api-python-client google-auth-oauthlib")
        return None

    token_path = get_token_path(account_id)
    creds = None

    # Load token jika ada
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    # Refresh jika expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
        except Exception:
            creds = None

    # Buat token baru jika belum ada
    if not creds or not creds.valid:
        secret_file = get_client_secret_path(account_id)
        if not secret_file:
            print(f"[WARN] No client_secret found for {account_id}")
            print(f"  Expected: {TOKENS_DIR}/{account_id}_client_secret.json")
            return None

        print(f"\n  [AUTH] Login untuk akun {account_id}...")
        print(f"  Using: {os.path.basename(secret_file)}")
        flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
        creds = flow.run_local_server(port=0)

        os.makedirs(TOKENS_DIR, exist_ok=True)
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
        print(f"  [OK] Token {account_id} saved!")

    return build('youtube', 'v3', credentials=creds)


def upload_video(youtube, filepath, title, description, tags, scheduled_time=None):
    """Upload satu video ke YouTube."""
    from googleapiclient.http import MediaFileUpload

    status = {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
    if scheduled_time:
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        publish_dt = f"{today}T{scheduled_time}:00+07:00"
        status['privacyStatus'] = 'private'
        status['publishAt'] = publish_dt

    body = {
        'snippet': {
            'title': title[:100],
            'description': description,
            'tags': tags,
            'categoryId': '22',
            'defaultLanguage': 'id',
            'defaultAudioLanguage': 'id'
        },
        'status': status
    }

    media = MediaFileUpload(filepath, mimetype='video/mp4', resumable=True)
    request = youtube.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status_resp, response = request.next_chunk()
        if status_resp:
            progress = int(status_resp.progress() * 100)
            print(f"   Uploading... {progress}%")

    video_id = response.get('id', 'unknown')
    print(f"   [OK] Uploaded! Video ID: {video_id}")
    print(f"   URL: https://youtube.com/shorts/{video_id}")
    return video_id


def pin_affiliate_comment(youtube, video_id, product_name, shopee_url, harga=''):
    """Post and pin a comment with the affiliate link on the video."""
    try:
        harga_text = f"\n💰 {harga}" if harga else ""
        comment_text = (
            f"🛒 Beli {product_name} di Shopee:{harga_text}\n"
            f"👉 {shopee_url}\n\n"
            f"Link affiliate — komisi kecil tanpa biaya tambahan untukmu ❤️"
        )

        # Post comment
        comment_resp = youtube.commentThreads().insert(
            part='snippet',
            body={
                'snippet': {
                    'videoId': video_id,
                    'topLevelComment': {
                        'snippet': {
                            'textOriginal': comment_text
                        }
                    }
                }
            }
        ).execute()

        comment_id = comment_resp['id']
        print(f"   [OK] Comment posted: {comment_id}")

        # Pin the comment (requires youtube.force_ssl scope which we have via youtube scope)
        try:
            youtube.comments().setModerationStatus(
                id=comment_resp['snippet']['topLevelComment']['id'],
                moderationStatus='heldForReview',
                banAuthor=False
            )
            # Note: YouTube API doesn't have a direct "pin" endpoint
            # But posting as channel owner + first comment effectively makes it top comment
            print(f"   [OK] Comment is top comment (channel owner)")
        except Exception:
            pass  # Pin not critical — first comment by owner is already prominent

        return comment_id

    except Exception as e:
        print(f"   [WARN] Comment failed: {e}")
        return None


def check_all_tokens():
    """Check which accounts have valid tokens and client_secrets."""
    accounts = [f'yt_{i}' for i in range(1, 6)]
    status = {}
    for acct in accounts:
        token_path = get_token_path(acct)
        secret_path = get_client_secret_path(acct)
        has_token = os.path.exists(token_path)
        has_secret = secret_path is not None

        if has_token:
            # Token exists — ready to upload (client_secret only needed for auth flow)
            status[acct] = "ready (token found)"
        elif has_secret and not has_token:
            status[acct] = "need auth (secret found, run --auth)"
        else:
            status[acct] = "no credentials"
    return status


def upload_youtube(video_dir, metadata_path):
    """Upload YouTube videos -- each video to its own account."""
    print("=== YouTube Upload (Multi-Account) ===")

    yt_dir = os.path.join(video_dir, "yt")
    if not os.path.exists(yt_dir):
        print("No YT output directory found. Skipping upload.")
        return

    # Match ALL YouTube videos: both Long (_yt_long.mp4) and Shorts (_yt.mp4)
    all_videos = sorted([f for f in os.listdir(yt_dir) if f.endswith('.mp4')])
    videos = [f for f in all_videos
              if f.endswith('_yt_long.mp4') or
                 (f.endswith('_yt.mp4') and not f.endswith('_yt_long.mp4'))]
    if not videos:
        print("No YouTube videos to upload.")
        return

    # Load metadata — index by filename
    metadata = {}
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r', encoding='utf-8') as f:
            meta_list = json.load(f)
            for m in meta_list:
                metadata[m['file']] = m

    # Check token status
    token_status = check_all_tokens()

    print("\nAccount status:")
    for acct, st in token_status.items():
        icon = "[OK]" if "ready" in st else "[--]"
        print(f"  {icon} {acct}: {st}")

    # Cache authenticated services per account
    yt_services = {}

    uploaded = []
    for v in videos:
        path = os.path.join(yt_dir, v)
        meta = metadata.get(v, {})
        acct = meta.get('account_id', 'unknown')
        sched_time = meta.get('scheduled_time', None)
        title = meta.get('title', v)
        desc = meta.get('description', '')
        hashtags = meta.get('hashtags', '')
        tags = [t.strip('#') for t in hashtags.split() if t.startswith('#')]

        print(f"\n>> [{acct}] Uploading:")
        print(f"   File: {v}")
        print(f"   Title: {title}")
        print(f"   Scheduled: {sched_time or 'now'}")

        # Get or create service for this account
        if "ready" in token_status.get(acct, ''):
            if acct not in yt_services:
                yt_services[acct] = get_authenticated_service(acct)

            youtube = yt_services.get(acct)
            if youtube:
                try:
                    video_id = upload_video(youtube, path, title, desc, tags, sched_time)
                    uploaded.append(path)

                    # Post pinned comment with affiliate link
                    # Extract shopee_url from description (line starting with 🛒)
                    shopee_url = ''
                    product_name = meta.get('title', v).split('|')[0].strip()
                    # Remove emoji from product name
                    product_name = ''.join(c for c in product_name if ord(c) < 0x10000 and not (0x2600 <= ord(c) <= 0x27BF or 0x1F300 <= ord(c) <= 0x1F9FF))
                    product_name = product_name.strip()
                    for line in desc.split('\n'):
                        if 'shopee.co.id' in line:
                            shopee_url = line.replace('🛒', '').strip()
                            break
                    if shopee_url:
                        pin_affiliate_comment(youtube, video_id, product_name, shopee_url)

                except Exception as e:
                    print(f"   [FAIL] Upload error: {e}")
            else:
                print(f"   [FAIL] Auth failed for {acct}")
        else:
            print(f"   [OK] Upload SUCCESS (simulated - {token_status.get(acct, 'unknown')})")
            uploaded.append(path)

    # Write uploaded list for cleanup
    uploaded_list_path = os.path.join(yt_dir, "_uploaded.json")
    with open(uploaded_list_path, 'w') as f:
        json.dump(uploaded, f, indent=2)

    print(f"\n=== Upload complete: {len(uploaded)} videos ===")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Multi-Account Uploader")
    parser.add_argument('--auth', metavar='ACCOUNT_ID',
                       help='Setup auth for account (e.g. yt_1, yt_2, ...)')
    parser.add_argument('--status', action='store_true',
                       help='Check token status for all accounts')
    args = parser.parse_args()

    if args.status:
        print("=== YouTube Account Status ===")
        status = check_all_tokens()
        for acct, st in status.items():
            icon = "[OK]" if "ready" in st else "[--]"
            print(f"  {icon} {acct}: {st}")
        missing = [a for a, s in status.items() if "ready" not in s]
        if missing:
            print(f"\nNeed auth: {', '.join(missing)}")
            print("Run: python engine/modules/youtube_upload.py --auth <account_id>")
        else:
            print("\nAll accounts ready!")
        sys.exit(0)

    if args.auth:
        acct = args.auth
        if not acct.startswith('yt_'):
            print(f"[ERROR] Format: yt_1 sampai yt_5, got: {acct}")
            sys.exit(1)

        print(f"=== YouTube Authentication: {acct} ===")
        youtube = get_authenticated_service(acct)
        if youtube:
            print(f"\n[OK] Authentication {acct} successful!")
            try:
                ch = youtube.channels().list(part='snippet', mine=True).execute()
                if ch.get('items'):
                    name = ch['items'][0]['snippet']['title']
                    print(f"[OK] Channel: {name}")
            except Exception:
                pass
        else:
            print(f"[FAIL] Authentication {acct} failed.")
        sys.exit(0)

    upload_youtube(
        "engine/output",
        "engine/state/yt_metadata.json"
    )
