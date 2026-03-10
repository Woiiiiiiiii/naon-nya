"""
hook_variant_generator.py
Spec: Variasikan hook text per akun YT agar video unik (anti-copyright).
Tidak generate teks baru — hanya modifikasi template yang sudah dipilih.

NOTE: NO EMOJI — font on render server has no emoji glyphs (renders as X-in-box)
"""
import json
import os
import sys
import random


def generate_hook_variants(yt_queue, tt_queue):
    """Vary hook text per YT account so each video is unique."""
    print("Generating hook variants per account...")

    # Process YT queue
    if os.path.exists(yt_queue):
        jobs = _read_queue(yt_queue)
        for job in jobs:
            acct = job.get('account_id', 'yt_1')
            acct_num = int(acct.split('_')[1]) if '_' in acct else 1
            job['hook'] = _vary_hook(job['hook'], acct_num)
        _write_queue(yt_queue, jobs)
        print(f"  YT: {len(jobs)} hooks varied")

    # TT queue: keep original hook (only 1 account)
    if os.path.exists(tt_queue):
        jobs = _read_queue(tt_queue)
        _write_queue(tt_queue, jobs)
        print(f"  TT: {len(jobs)} hooks styled")

    print("Hook variant generation complete.")


def _vary_hook(hook_text, account_num):
    """Create a unique variant of the hook for each account. No emoji."""
    if account_num == 1:
        return hook_text
    elif account_num == 2:
        return f"{hook_text} Wajib tau!"
    elif account_num == 3:
        if not hook_text.endswith('?'):
            return f"Tau gak? {hook_text}"
        return hook_text
    elif account_num == 4:
        return f"{hook_text.rstrip('!?.')}!!"
    else:
        prefixes = ["Cek ini -", "Wajib lihat -", "Jangan lewatkan -"]
        return f"{random.choice(prefixes)} {hook_text}"


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
    generate_hook_variants(
        "engine/queue/yt_queue.jsonl",
        "engine/queue/tt_queue.jsonl"
    )
