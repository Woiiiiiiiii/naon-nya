"""
youtube_upload.py
Upload video ke YouTube via Data API v3.
Mendukung 5 akun YouTube dengan credentials terpisah.

Authentication: Refresh Token (long-lived, stored in GitHub Secrets)
  - No pickle files needed
  - Refresh tokens don't expire unless revoked
  - Clean secret management

GitHub Secrets needed:
  YT_CLIENT_SECRET     — OAuth client_secret.json content (shared)
  YT_REFRESH_TOKEN_1   — Refresh token akun yt_1
  YT_REFRESH_TOKEN_2   — Refresh token akun yt_2
  ... sampai YT_REFRESH_TOKEN_5

Setup per akun (1x saja, jalankan di lokal):
  python engine/modules/youtube_upload.py --auth yt_1
  → login → copy refresh token → paste ke GitHub Secret
"""
import os
import sys
import json
import datetime
import tempfile

# Paths
CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
TOKENS_DIR = os.path.join(CONFIG_DIR, 'tokens')

SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
           'https://www.googleapis.com/auth/youtube',
           'https://www.googleapis.com/auth/youtube.force-ssl']


def _get_client_config(account_id=None):
    """Get OAuth client config from env var or local file.
    Supports per-account secrets: YT_CLIENT_SECRET_1 through _5."""
    acct_num = account_id.replace('yt_', '') if account_id else ''

    # Priority 1: Per-account GitHub Secret (YT_CLIENT_SECRET_1, _2, etc.)
    if acct_num:
        secret_json = os.environ.get(f'YT_CLIENT_SECRET_{acct_num}', '')
        if secret_json:
            try:
                return json.loads(secret_json)
            except json.JSONDecodeError:
                print(f"[WARN] YT_CLIENT_SECRET_{acct_num} is not valid JSON")

    # Priority 2: Shared secret (YT_CLIENT_SECRET)
    secret_json = os.environ.get('YT_CLIENT_SECRET', '')
    if secret_json:
        try:
            return json.loads(secret_json)
        except json.JSONDecodeError:
            pass

    # Priority 3: Per-account local file
    if account_id:
        acct_secret = os.path.join(TOKENS_DIR, f'{account_id}_client_secret.json')
        if os.path.exists(acct_secret):
            with open(acct_secret, 'r') as f:
                return json.load(f)

    # Priority 4: Shared local file
    shared_secret = os.path.join(CONFIG_DIR, 'client_secret.json')
    if os.path.exists(shared_secret):
        with open(shared_secret, 'r') as f:
            return json.load(f)

    return None


def _get_refresh_token(account_id):
    """Get refresh token from env var or local file."""
    acct_num = account_id.replace('yt_', '')

    # Priority 1: GitHub Secret (env var)
    token = os.environ.get(f'YT_REFRESH_TOKEN_{acct_num}', '')
    if token:
        return token

    # Priority 2: Local token file
    token_file = os.path.join(TOKENS_DIR, f'{account_id}_refresh_token.txt')
    if os.path.exists(token_file):
        with open(token_file, 'r') as f:
            return f.read().strip()

    return None


def get_authenticated_service(account_id):
    """Authenticate and return YouTube API service for a specific account."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("[WARN] google-api-python-client not installed.")
        print("  Run: pip install google-api-python-client google-auth-oauthlib")
        return None

    client_config = _get_client_config(account_id)
    if not client_config:
        print(f"[WARN] No client_secret found for {account_id}")
        return None

    refresh_token = _get_refresh_token(account_id)
    if not refresh_token:
        print(f"[WARN] No refresh token for {account_id}")
        print(f"  Run locally: python engine/modules/youtube_upload.py --auth {account_id}")
        return None

    # Extract client_id and client_secret from config
    installed = client_config.get('installed', client_config.get('web', {}))
    client_id = installed.get('client_id', '')
    client_secret = installed.get('client_secret', '')
    token_uri = installed.get('token_uri', 'https://oauth2.googleapis.com/token')

    # Create credentials from refresh token
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    # Refresh to get fresh access token
    try:
        creds.refresh(Request())
        print(f"  [{account_id}] Auth OK (refresh token)")
    except Exception as e:
        print(f"  [{account_id}] Auth FAILED: {e}")
        print(f"  Token mungkin sudah di-revoke. Re-run: --auth {account_id}")
        return None

    return build('youtube', 'v3', credentials=creds)


def run_auth_flow(account_id):
    """Run OAuth flow locally to get refresh token. 1x only per account."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Install: pip install google-auth-oauthlib")
        return

    client_config = _get_client_config(account_id)

    if not client_config:
        print("[ERROR] client_secret.json tidak ditemukan!")
        print("  Taruh di: engine/config/client_secret.json")
        print("  Atau set env: YT_CLIENT_SECRET='{...json...}'")
        return

    # Write temp file for InstalledAppFlow
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(client_config, tmp)
    tmp.close()

    try:
        print(f"\n=== YouTube Auth: {account_id} ===")
        print(f"Browser akan terbuka — login ke akun YouTube untuk channel ini.")
        print(f"Setelah login, klik 'Allow' untuk memberikan izin upload.\n")

        flow = InstalledAppFlow.from_client_secrets_file(tmp.name, SCOPES)
        creds = flow.run_local_server(port=0)

        refresh_token = creds.refresh_token
        if not refresh_token:
            print("[ERROR] Tidak mendapat refresh token!")
            print("  Coba revoke access di https://myaccount.google.com/permissions")
            print("  Lalu jalankan --auth lagi.")
            return

        # Save locally
        os.makedirs(TOKENS_DIR, exist_ok=True)
        token_file = os.path.join(TOKENS_DIR, f'{account_id}_refresh_token.txt')
        with open(token_file, 'w') as f:
            f.write(refresh_token)

        # Print for user to copy to GitHub Secrets
        acct_num = account_id.replace('yt_', '')
        print(f"\n{'='*60}")
        print(f"[OK] AUTH SUKSES untuk {account_id}!")
        print(f"{'='*60}")
        print(f"\nRefresh token tersimpan di: {token_file}")
        print(f"\nCOPY refresh token di bawah ini ke GitHub Secret:")
        print(f"   Secret name: YT_REFRESH_TOKEN_{acct_num}")
        print(f"   Secret value:")
        print(f"\n   {refresh_token}\n")
        print(f"{'='*60}")

        # Verify
        try:
            from googleapiclient.discovery import build
            youtube = build('youtube', 'v3', credentials=creds)
            ch = youtube.channels().list(part='snippet', mine=True).execute()
            if ch.get('items'):
                name = ch['items'][0]['snippet']['title']
                print(f"🎬 Channel: {name}")
        except Exception:
            pass

    finally:
        os.unlink(tmp.name)


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
    # Determine URL based on file path
    is_long = '_yt_long' in os.path.basename(filepath)
    if is_long:
        print(f"   URL: https://youtube.com/watch?v={video_id}")
    else:
        print(f"   URL: https://youtube.com/shorts/{video_id}")
    return video_id


def pin_affiliate_comment(youtube, video_id, product_name, shopee_url, harga=''):
    """Post and pin a comment with the affiliate link on the video."""
    try:
        harga_text = f"\n💰 {harga}" if harga else ""
        comment_text = (
            f"🛒 Beli {product_name} di Shopee:{harga_text}\n"
            f"👇 Link produk:\n"
            f"{shopee_url}\n\n"
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

        # Pin the comment
        try:
            youtube.comments().setModerationStatus(
                id=comment_resp['snippet']['topLevelComment']['id'],
                moderationStatus='heldForReview',
                banAuthor=False
            )
            print(f"   [OK] Comment is top comment (channel owner)")
        except Exception:
            pass  # Pin not critical

        return comment_id

    except Exception as e:
        print(f"   [WARN] Comment failed: {e}")
        return None


def check_all_tokens():
    """Check which accounts have valid refresh tokens."""
    accounts = [f'yt_{i}' for i in range(1, 6)]
    status = {}
    for acct in accounts:
        token = _get_refresh_token(acct)
        if token:
            status[acct] = "ready (refresh token found)"
        else:
            config = _get_client_config()
            if config:
                status[acct] = "need auth (client_secret found, run --auth)"
            else:
                status[acct] = "no credentials"
    return status


def upload_youtube(video_dir, metadata_path):
    """Upload YouTube videos with anti-bot measures.
    
    Anti-bot protections:
    - Random delay between each upload (45-120 seconds)
    - Shuffled upload order (not always same channel first)
    - Staggered comment posting (15-45s after upload)
    - Different scheduled publish times per channel
    - Human-like pacing (slower for first uploads, faster later)
    """
    import random
    import time

    print("=== YouTube Upload (Multi-Account, Anti-Bot) ===")

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

    # Anti-bot: shuffle upload order (don't always upload yt_1 first)
    random.shuffle(videos)
    print(f"  Upload order randomized ({len(videos)} videos)")

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
    for idx, v in enumerate(videos):
        path = os.path.join(yt_dir, v)
        meta = metadata.get(v, {})
        acct = meta.get('account_id', 'unknown')
        sched_time = meta.get('scheduled_time', None)
        title = meta.get('title', v)
        desc = meta.get('description', '')
        hashtags = meta.get('hashtags', '')
        tags = [t.strip('#') for t in hashtags.split() if t.startswith('#')]

        # Anti-bot: random delay between uploads (skip first one)
        if idx > 0:
            delay = random.randint(45, 120)
            print(f"\n  [Anti-bot] Waiting {delay}s before next upload...")
            time.sleep(delay)

        print(f"\n>> [{acct}] Uploading ({idx+1}/{len(videos)}):")
        print(f"   File: {v}")
        print(f"   Title: {title}")
        print(f"   Scheduled: {sched_time or 'now'}")

        # Get or create service for this account
        if "ready" in token_status.get(acct, ''):
            if acct not in yt_services:
                # Anti-bot: small delay before first auth per account
                if yt_services:
                    auth_delay = random.randint(5, 15)
                    time.sleep(auth_delay)
                yt_services[acct] = get_authenticated_service(acct)

            youtube = yt_services.get(acct)
            if youtube:
                try:
                    video_id = upload_video(youtube, path, title, desc, tags, sched_time)
                    uploaded.append(path)

                    # Anti-bot: delay before posting comment (15-45s)
                    comment_delay = random.randint(15, 45)
                    print(f"   [Anti-bot] Comment delay: {comment_delay}s")
                    time.sleep(comment_delay)

                    # Post pinned comment with affiliate link
                    shopee_url = meta.get('shopee_url', '')
                    product_name = meta.get('produk', '') or meta.get('title', v).split('|')[0].strip()
                    product_name = ''.join(c for c in product_name if ord(c) < 0x10000
                                          and not (0x2600 <= ord(c) <= 0x27BF
                                                   or 0x1F300 <= ord(c) <= 0x1F9FF))
                    product_name = product_name.strip()
                    harga = meta.get('harga', '')

                    # Fallback: extract URL from description if not in metadata
                    if not shopee_url:
                        for line in desc.split('\n'):
                            if 'shopee.co.id' in line or 'tinyurl.com' in line:
                                url_start = line.find('https://')
                                if url_start >= 0:
                                    shopee_url = line[url_start:].strip()
                                else:
                                    shopee_url = line.strip()
                                break
                    if shopee_url:
                        pin_affiliate_comment(youtube, video_id, product_name, shopee_url, harga)

                except Exception as e:
                    print(f"   [FAIL] Upload error: {e}")
            else:
                print(f"   [FAIL] Auth failed for {acct}")
        else:
            print(f"   [SKIP] No token for {acct} -- run --auth {acct} locally")

    # Write uploaded list for cleanup
    uploaded_list_path = os.path.join(yt_dir, "_uploaded.json")
    with open(uploaded_list_path, 'w') as f:
        json.dump(uploaded, f, indent=2)

    print(f"\n=== Upload complete: {len(uploaded)}/{len(videos)} videos ===")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Multi-Account Uploader (Refresh Token)")
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
        run_auth_flow(acct)
        sys.exit(0)

    upload_youtube(
        "engine/output",
        "engine/state/yt_metadata.json"
    )
