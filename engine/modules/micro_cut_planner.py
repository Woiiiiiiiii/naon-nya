"""
micro_cut_planner.py
Plans scene timing per account to make each video structurally unique.
Different accounts get different durations for hook/masalah/solusi/CTA scenes.
"""
import json
import os
import sys
import random

# Scene timing ranges (min, max) in seconds
SCENE_RANGES = {
    "hook":    (2.0, 4.0),
    "masalah": (3.0, 5.0),
    "solusi":  (3.0, 5.0),
    "cta":     (2.5, 4.0),
}

def plan_micro_cuts(yt_queue, tt_queue):
    """Assign unique scene timings per account."""
    print("Planning micro-cuts per account...")

    if os.path.exists(yt_queue):
        jobs = _read_queue(yt_queue)
        for job in jobs:
            acct_num = int(job.get('account_id', 'yt_1').split('_')[1])
            random.seed(hash(f"{job.get('date','')}{job['produk_id']}{acct_num}"))
            timings = _generate_timings()
            job['scene_timings'] = timings
        _write_queue(yt_queue, jobs)
        print(f"  YT: {len(jobs)} timing plans created")

    if os.path.exists(tt_queue):
        jobs = _read_queue(tt_queue)
        for job in jobs:
            random.seed(hash(f"{job.get('date','')}{job['produk_id']}tt"))
            # TT: shorter hook (grab attention faster), longer CTA
            timings = _generate_timings(tt_mode=True)
            job['scene_timings'] = timings
        _write_queue(tt_queue, jobs)
        print(f"  TT: {len(jobs)} timing plans created")

    print("Micro-cut planning complete.")


def _generate_timings(tt_mode=False):
    """Generate scene timings that sum to ~15s."""
    if tt_mode:
        # TikTok: fast hook, punchy
        hook_dur = round(random.uniform(1.5, 2.5), 1)
        masalah_dur = round(random.uniform(3.0, 4.5), 1)
        solusi_dur = round(random.uniform(3.5, 5.0), 1)
    else:
        hook_dur = round(random.uniform(*SCENE_RANGES["hook"]), 1)
        masalah_dur = round(random.uniform(*SCENE_RANGES["masalah"]), 1)
        solusi_dur = round(random.uniform(*SCENE_RANGES["solusi"]), 1)
    
    # CTA fills remaining time to reach ~15s
    used = hook_dur + masalah_dur + solusi_dur
    cta_dur = round(max(2.0, 15.0 - used), 1)

    return {
        "hook": {"start": 0, "duration": hook_dur},
        "masalah": {"start": hook_dur, "duration": masalah_dur},
        "solusi": {"start": hook_dur + masalah_dur, "duration": solusi_dur},
        "cta": {"start": used, "duration": cta_dur}
    }


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
    plan_micro_cuts(
        "engine/queue/yt_queue.jsonl",
        "engine/queue/tt_queue.jsonl"
    )
