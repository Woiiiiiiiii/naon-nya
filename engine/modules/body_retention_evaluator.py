"""
body_retention_evaluator.py
QC module: evaluates if video has enough scene changes and timing quality.
Checks scene_timings metadata to ensure min 3 scenes and no scene < 1.5s.
"""
import json
import os
import sys

def evaluate_retention(yt_queue, tt_queue):
    """Evaluate if queued videos meet retention quality standards."""
    print("Evaluating retention quality...")

    all_ok = True

    for queue_path, label in [(yt_queue, "YT"), (tt_queue, "TT")]:
        if not os.path.exists(queue_path):
            continue

        jobs = []
        with open(queue_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    jobs.append(json.loads(line))

        for job in jobs:
            pid = job['produk_id']
            acct = job.get('account_id', 'unknown')
            timings = job.get('scene_timings', {})

            issues = []

            # Check minimum scene count
            if len(timings) < 3:
                issues.append(f"Only {len(timings)} scenes (min 3)")

            # Check no scene is too short
            for scene, t in timings.items():
                dur = t.get('duration', 0)
                if dur < 1.5:
                    issues.append(f"Scene '{scene}' too short: {dur}s (min 1.5s)")

            # Check total duration is ≈ 15s
            total = sum(t.get('duration', 0) for t in timings.values())
            if total < 12 or total > 18:
                issues.append(f"Total duration {total}s out of range [12-18s]")

            if issues:
                print(f"  [WARN] {label}/{acct}/{pid}: {'; '.join(issues)}")
                all_ok = False
            else:
                print(f"  [OK] {label}/{acct}/{pid}: {len(timings)} scenes, {total:.1f}s total")

    if all_ok:
        print("Retention evaluation: All videos PASS")
    else:
        print("Retention evaluation: Issues found (see warnings above)")
        # Don't exit — warnings only, not fatal


if __name__ == "__main__":
    evaluate_retention(
        "engine/queue/yt_queue.jsonl",
        "engine/queue/tt_queue.jsonl"
    )
