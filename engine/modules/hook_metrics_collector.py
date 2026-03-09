"""
hook_metrics_collector.py
Tracks hook template performance. Creates/updates hook_metrics.csv.
Data is placeholder — meant to be updated manually with real impressions/CTR data.
"""
import json
import os
import sys
import pandas as pd
import datetime

def collect_hook_metrics(yt_queue, tt_queue, output_file):
    """Record which hooks were used in this batch for later performance tracking."""
    print("Collecting hook metrics...")

    records = []
    for queue_path, platform in [(yt_queue, "youtube"), (tt_queue, "tiktok")]:
        if not os.path.exists(queue_path):
            continue
        with open(queue_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                job = json.loads(line)
                records.append({
                    'date': job.get('date', datetime.datetime.now().strftime("%Y%m%d")),
                    'produk_id': job['produk_id'],
                    'account_id': job.get('account_id', 'unknown'),
                    'platform': platform,
                    'hook_text': job.get('hook', ''),
                    'impressions': 0,    # To be filled manually
                    'clicks': 0,         # To be filled manually
                    'ctr': 0.0           # To be calculated
                })

    if records:
        df = pd.DataFrame(records)
        if os.path.exists(output_file):
            df.to_csv(output_file, mode='a', header=False, index=False)
        else:
            df.to_csv(output_file, index=False)
        print(f"  Recorded {len(records)} hook entries to {output_file}")
    else:
        print("  No hooks to record")

    print("Hook metrics collection complete.")


if __name__ == "__main__":
    collect_hook_metrics(
        "engine/queue/yt_queue.jsonl",
        "engine/queue/tt_queue.jsonl",
        "engine/state/hook_metrics.csv"
    )
