"""
body_micro_editor.py
Applies micro-variations to each video's parameters to ensure binary uniqueness.
Each account gets slightly different: background shade, scene timing offsets, text position.
"""
import json
import os
import sys
import random
import hashlib

def micro_edit(yt_queue, tt_queue):
    """Apply micro-edits per account for anti-copyright uniqueness."""
    print("Applying micro-edits for video uniqueness...")

    if os.path.exists(yt_queue):
        jobs = _read_queue(yt_queue)
        for job in jobs:
            acct = job.get('account_id', 'yt_1')
            seed = hashlib.md5(f"{job.get('date','')}{job['produk_id']}{acct}".encode()).hexdigest()
            random.seed(seed)

            job['micro_edits'] = {
                # Slightly vary background color per account (RGB offset ±15)
                'bg_offset': [random.randint(-15, 15) for _ in range(3)],
                # Vary text Y positions (±30px)
                'text_y_offset': random.randint(-30, 30),
                # Vary image scale (95%-105%)
                'image_scale': round(random.uniform(0.95, 1.05), 3),
                # Vary font size (±3px)
                'font_size_offset': random.randint(-3, 3),
                # Unique seed for this variant
                'variant_seed': seed[:8]
            }
        _write_queue(yt_queue, jobs)
        print(f"  YT: {len(jobs)} micro-edits applied")

    if os.path.exists(tt_queue):
        jobs = _read_queue(tt_queue)
        for job in jobs:
            seed = hashlib.md5(f"{job.get('date','')}{job['produk_id']}tt".encode()).hexdigest()
            random.seed(seed)
            job['micro_edits'] = {
                'bg_offset': [random.randint(-10, 10) for _ in range(3)],
                'text_y_offset': random.randint(-20, 20),
                'image_scale': round(random.uniform(0.97, 1.03), 3),
                'font_size_offset': random.randint(-2, 2),
                'variant_seed': seed[:8]
            }
        _write_queue(tt_queue, jobs)
        print(f"  TT: {len(jobs)} micro-edits applied")

    print("Micro-editing complete.")


def _read_queue(path):
    jobs = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                jobs.append(json.loads(line))
    return jobs

def _write_queue(path, jobs):
    with open(path, 'w', encoding='utf-8') as f:
        for job in jobs:
            f.write(json.dumps(job, ensure_ascii=False) + '\n')


if __name__ == "__main__":
    micro_edit(
        "engine/queue/yt_queue.jsonl",
        "engine/queue/tt_queue.jsonl"
    )
