"""
delete_after_upload.py
Cleanup setelah YouTube auto-upload.
- Hapus video YouTube yang sudah di-upload
- Hapus YT metadata (yt_metadata.json)
- TT/FB video + metadata TIDAK dihapus di sini (dikirim via email dulu)
"""
import os
import sys
import json


def cleanup(video_dir):
    """Delete uploaded YT videos + YT metadata only."""
    print("=== Post-Upload Cleanup (YouTube Only) ===")

    yt_dir = os.path.join(video_dir, "yt")
    state_dir = os.path.join(os.path.dirname(video_dir), "state")

    # 1. YouTube: auto-delete uploaded videos
    uploaded_list = os.path.join(yt_dir, "_uploaded.json")
    if os.path.exists(uploaded_list):
        with open(uploaded_list, 'r') as f:
            files = json.load(f)

        deleted = 0
        for fpath in files:
            if os.path.exists(fpath):
                os.remove(fpath)
                print(f"  [DEL] {os.path.basename(fpath)}")
                deleted += 1

        os.remove(uploaded_list)
        print(f"  YouTube videos: {deleted} files deleted")
    else:
        print("  No YouTube upload list found. Nothing to clean.")

    # 2. Delete YT metadata (already used by YouTube upload)
    yt_meta = os.path.join(state_dir, "yt_metadata.json")
    if os.path.exists(yt_meta):
        os.remove(yt_meta)
        print(f"  [DEL] yt_metadata.json")

    # 3. TT/FB videos + metadata: kept for email delivery step
    print("  TT/FB files kept for email delivery.")
    print("Cleanup complete.")


if __name__ == "__main__":
    cleanup("engine/output")
