"""
cta_selector.py
Selects CTA templates from library for both YT and TT queues.
YT: rotates through YouTube-specific CTAs per account.
TT: gets the top-performing TikTok CTA.
"""
import json
import os
import sys

def select_cta(yt_queue, tt_queue, cta_library):
    print("Selecting CTAs from library...")
    
    if not os.path.exists(cta_library):
        print(f"Error: {cta_library} not found.")
        return
        
    with open(cta_library, 'r') as f:
        ctas = json.load(f)
    
    yt_ctas = sorted(
        [c for c in ctas if c.get('platform') == 'youtube'],
        key=lambda c: c.get('click_score', 0), reverse=True
    )
    tt_ctas = sorted(
        [c for c in ctas if c.get('platform') == 'tiktok'],
        key=lambda c: c.get('click_score', 0), reverse=True
    )
    
    if not yt_ctas: yt_ctas = ctas
    if not tt_ctas: tt_ctas = ctas
    
    # Process YT queue
    if os.path.exists(yt_queue):
        jobs = _read_queue(yt_queue)
        for job in jobs:
            v_id = job.get('variant_id', 1)
            cta_idx = (v_id - 1) % len(yt_ctas)
            job['cta'] = yt_ctas[cta_idx]['template']
            job['cta_id'] = yt_ctas[cta_idx]['id']
        _write_queue(yt_queue, jobs)
        print(f"  YT: {len(jobs)} CTAs selected from {len(yt_ctas)} YT templates")
    
    # Process TT queue
    if os.path.exists(tt_queue):
        jobs = _read_queue(tt_queue)
        for job in jobs:
            job['cta'] = tt_ctas[0]['template']
            job['cta_id'] = tt_ctas[0]['id']
        _write_queue(tt_queue, jobs)
        print(f"  TT: {len(jobs)} CTAs selected (top performer)")
    
    print("CTA selection complete.")


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
    select_cta(
        "engine/queue/yt_queue.jsonl",
        "engine/queue/tt_queue.jsonl",
        "engine/library/cta_library.json"
    )
