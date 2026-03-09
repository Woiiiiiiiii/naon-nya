"""
gcs_upload.py
Upload video TikTok + Facebook ke Google Cloud Storage.
Video otomatis dihapus dari runner setelah upload berhasil.

Setup:
  1. Buat GCS bucket di Google Cloud Console
  2. Buat Service Account → download JSON key
  3. Simpan sebagai GitHub Secret: GCS_SA_KEY (isi = konten JSON)
  4. Set bucket name di engine_config.yaml: gcs.bucket

Struktur di GCS:
  gs://BUCKET/
    YYYY-MM-DD/pagi/
      tt/  ← video TikTok
      fb/  ← video Facebook
    YYYY-MM-DD/sore/
      ...
"""
import os
import sys
import json
import datetime
import yaml


def load_config():
    """Load engine config."""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'engine_config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def upload_to_gcs(video_dir, slot):
    """Upload TT+FB videos to Google Cloud Storage, then delete local files."""
    print("=== Google Cloud Storage Upload ===")

    config = load_config()
    bucket_name = config.get('gcs', {}).get('bucket', '')

    if not bucket_name:
        print("[WARN] GCS bucket not configured in engine_config.yaml")
        print("  Set gcs.bucket to your bucket name")
        print("  Skipping GCS upload.")
        return

    # Try to import GCS client
    try:
        from google.cloud import storage
    except ImportError:
        print("[WARN] google-cloud-storage not installed.")
        print("  Run: pip install google-cloud-storage")
        print("  Skipping GCS upload.")
        return

    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
    except Exception as e:
        print(f"[WARN] GCS auth failed: {e}")
        print("  Make sure GOOGLE_APPLICATION_CREDENTIALS is set")
        print("  Skipping GCS upload.")
        return

    today = datetime.datetime.now().strftime("%Y-%m-%d")

    # Upload metadata JSONs first (for manual posting reference)
    state_dir = os.path.join(os.path.dirname(video_dir), 'state')
    metadata_files = {
        'tt': os.path.join(state_dir, 'tt_metadata.json'),
        'fb': os.path.join(state_dir, 'fb_metadata.json'),
    }
    for platform, meta_path in metadata_files.items():
        if os.path.exists(meta_path):
            gcs_path = f"{today}/{slot}/{platform}/metadata.json"
            try:
                blob = bucket.blob(gcs_path)
                blob.upload_from_filename(meta_path, content_type='application/json')
                blob.make_public()
                print(f"  [OK] {platform.upper()} metadata -> gs://{bucket_name}/{gcs_path}")
                print(f"       -> {blob.public_url}")
                os.remove(meta_path)
                print(f"  [DEL] Local metadata deleted")
            except Exception as e:
                print(f"  [WARN] {platform.upper()} metadata upload failed: {e}")

    platforms = {
        'tt': os.path.join(video_dir, 'tt'),
        'fb': os.path.join(video_dir, 'fb'),
    }

    total_uploaded = 0
    total_deleted = 0

    for platform, platform_dir in platforms.items():
        if not os.path.exists(platform_dir):
            print(f"\n[{platform.upper()}] Directory not found. Skipping.")
            continue

        videos = sorted([f for f in os.listdir(platform_dir) if f.endswith('.mp4')])
        if not videos:
            print(f"\n[{platform.upper()}] No videos to upload.")
            continue

        print(f"\n[{platform.upper()}] Uploading {len(videos)} videos to GCS...")

        for video_file in videos:
            local_path = os.path.join(platform_dir, video_file)
            gcs_path = f"{today}/{slot}/{platform}/{video_file}"

            try:
                blob = bucket.blob(gcs_path)
                blob.upload_from_filename(local_path, content_type='video/mp4')

                # Make publicly accessible for easy download
                blob.make_public()
                public_url = blob.public_url

                print(f"  [OK] {video_file}")
                print(f"       -> gs://{bucket_name}/{gcs_path}")
                print(f"       -> {public_url}")
                total_uploaded += 1

                # Delete local file after successful upload
                os.remove(local_path)
                print(f"  [DEL] Local file deleted")
                total_deleted += 1

            except Exception as e:
                print(f"  [FAIL] {video_file}: {e}")
                print(f"  [KEEP] Local file kept (upload failed)")

    print(f"\n=== GCS Upload Complete ===")
    print(f"  Uploaded: {total_uploaded} videos")
    print(f"  Deleted locally: {total_deleted} files")
    print(f"  Location: gs://{bucket_name}/{today}/{slot}/")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Upload TT+FB videos to GCS")
    parser.add_argument('--slot', default='pagi', help='Current slot (pagi/sore/malam)')
    args = parser.parse_args()

    upload_to_gcs("engine/output", args.slot)
