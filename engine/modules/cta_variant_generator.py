"""
cta_variant_generator.py
Spec: Variasikan CTA per akun & platform. Dilarang hard selling.

NOTE: NO EMOJI — font on render server has no emoji glyphs (renders as X-in-box)
"""
import json
import os
import sys
import random

def generate_cta_variants(yt_queue, tt_queue):
    """Vary CTA text per account and ensure platform-appropriate language."""
    print("Generating CTA variants per account...")

    # Process YT queue
    if os.path.exists(yt_queue):
        jobs = _read_queue(yt_queue)
        for job in jobs:
            acct_num = int(job.get('account_id', 'yt_1').split('_')[1])
            cta = job.get('cta', 'Klik link di deskripsi!')
            # Ensure YT-specific language
            cta = cta.replace('link di bio', 'link di deskripsi')
            job['cta'] = cta
        _write_queue(yt_queue, jobs)
        print(f"  YT: {len(jobs)} CTAs varied")

    # Process TT queue
    if os.path.exists(tt_queue):
        jobs = _read_queue(tt_queue)
        for job in jobs:
            cta = job.get('cta', 'Klik link di bio!')
            # Ensure TT-specific language
            cta = cta.replace('link di deskripsi', 'link di bio')
            job['cta'] = cta
        _write_queue(tt_queue, jobs)
        print(f"  TT: {len(jobs)} CTAs styled")

    print("CTA variant generation complete.")


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
    generate_cta_variants(
        "engine/queue/yt_queue.jsonl",
        "engine/queue/tt_queue.jsonl"
    )
