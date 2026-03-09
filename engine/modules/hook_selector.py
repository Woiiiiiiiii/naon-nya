"""
hook_selector.py
Selects hook templates from library for both YT and TT queues.
YT: each account gets a different hook (rotation by variant_id).
TT: gets the top-performing hook.
"""
import json
import os
import sys

def select_hook(yt_queue, tt_queue, hook_library):
    print("Selecting hooks from library...")
    
    if not os.path.exists(hook_library):
        print(f"Error: {hook_library} not found.")
        return
        
    with open(hook_library, 'r') as f:
        hooks = json.load(f)
    
    # Sort by CTR score descending
    hooks_sorted = sorted(hooks, key=lambda h: h.get('ctr_score', 0), reverse=True)
    
    # Process YT queue
    if os.path.exists(yt_queue):
        jobs = _read_queue(yt_queue)
        for job in jobs:
            v_id = job.get('variant_id', 1)
            hook_idx = (v_id - 1) % len(hooks_sorted)
            job['hook'] = hooks_sorted[hook_idx]['template']
            job['hook_id'] = hooks_sorted[hook_idx]['id']
        _write_queue(yt_queue, jobs)
        print(f"  YT: {len(jobs)} hooks selected")
    
    # Process TT queue
    if os.path.exists(tt_queue):
        jobs = _read_queue(tt_queue)
        for job in jobs:
            # TT gets the top-performing hook
            job['hook'] = hooks_sorted[0]['template']
            job['hook_id'] = hooks_sorted[0]['id']
        _write_queue(tt_queue, jobs)
        print(f"  TT: {len(jobs)} hooks selected (top performer)")
    
    print(f"Hook selection complete. Library: {len(hooks)} templates")


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
    select_hook(
        "engine/queue/yt_queue.jsonl",
        "engine/queue/tt_queue.jsonl",
        "engine/library/hook_library.json"
    )
