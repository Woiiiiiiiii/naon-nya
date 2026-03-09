"""
yt_performance_analyzer.py
Analyzes performance data and creates optimization queue.
Logic:
  - CTR < 4% → optimize title/thumbnail  
  - Retention < 30% → optimize description/tags
  - Views stagnant 2 weeks → full refresh
  - Good CTR but low views → expand tags
  - Low engagement → stronger CTA in description
  - High performance (CTR>6%, retention>50%) → save as success pattern
"""
import os
import json
import datetime

STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')
PERF_FILE = os.path.join(STATE_DIR, 'performance_data.json')
OPT_QUEUE_FILE = os.path.join(STATE_DIR, 'optimization_queue.json')
PATTERNS_FILE = os.path.join(STATE_DIR, 'success_patterns.json')

OPTIMIZE_COOLDOWN_DAYS = 14  # Don't re-optimize within 14 days


def _load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_latest_weeks(video_data):
    """Get the 2 most recent weekly data points."""
    weeks = sorted([k for k in video_data.keys() if k.startswith('minggu_')])
    return weeks[-2:] if len(weeks) >= 2 else weeks


def _estimate_ctr(video_data, week_key):
    """Estimate CTR from available data."""
    w = video_data.get(week_key, {})
    impressions = w.get('impressions', 0)
    views = w.get('views', 0)
    if impressions > 0:
        return views / impressions
    return 0.05  # Default estimate


def analyze_performance():
    """Analyze all video performance and generate optimization queue."""
    print("=== YT Performance Analyzer ===")

    perf_data = _load_json(PERF_FILE)
    opt_queue = _load_json(OPT_QUEUE_FILE)
    patterns = _load_json(PATTERNS_FILE)

    today = datetime.datetime.now()
    new_tasks = []

    for account_id, videos in perf_data.items():
        print(f"\n  📊 Analyzing: {account_id}")

        for video_id, vdata in videos.items():
            weeks = _get_latest_weeks(vdata)
            if not weeks:
                continue

            latest_week = weeks[-1]
            latest = vdata.get(latest_week, {})

            # Skip if recently optimized
            last_opt = vdata.get('last_optimized', '')
            if last_opt:
                try:
                    opt_date = datetime.datetime.strptime(last_opt, '%Y-%m-%d')
                    if (today - opt_date).days < OPTIMIZE_COOLDOWN_DAYS:
                        continue
                except ValueError:
                    pass

            views = latest.get('views', 0)
            likes = latest.get('likes', 0)
            retention = latest.get('retention_rate', 0.35)
            ctr = _estimate_ctr(vdata, latest_week)

            # Engagement rate
            engagement = likes / max(views, 1)

            actions = []
            priority = 'low'

            # === Analysis Rules ===

            # CTR di bawah 4% → optimize title/thumbnail
            if ctr < 0.04:
                actions.append('optimize_title')
                actions.append('optimize_thumbnail')
                priority = 'high'

            # Retention di bawah 30% → optimize description/tags
            if retention < 0.30:
                actions.append('optimize_description')
                actions.append('optimize_tags')
                priority = 'high' if priority != 'high' else priority

            # Views stagnan 2 minggu
            if len(weeks) >= 2:
                prev = vdata.get(weeks[-2], {})
                prev_views = prev.get('views', 0)
                if views > 0 and prev_views > 0:
                    growth = (views - prev_views) / max(prev_views, 1)
                    if growth < 0.05:  # Less than 5% growth
                        actions.append('full_refresh')
                        priority = 'high'

            # Good CTR but low views → expand tags
            if ctr >= 0.04 and views < 500:
                actions.append('expand_tags')
                priority = 'medium'

            # Low engagement → stronger CTA
            if engagement < 0.02 and views > 100:
                actions.append('strengthen_cta')
                priority = 'medium'

            # === Success Pattern Detection ===
            if ctr >= 0.06 and retention >= 0.50:
                # Save as success pattern
                if 'success_patterns' not in patterns:
                    patterns['success_patterns'] = []
                patterns['success_patterns'].append({
                    'account': account_id,
                    'video_id': video_id,
                    'title': vdata.get('judul', ''),
                    'ctr': ctr,
                    'retention': retention,
                    'views': views,
                    'kategori': vdata.get('kategori', ''),
                    'recorded_at': today.strftime('%Y-%m-%d'),
                })
                # Don't optimize high performers
                continue

            if actions:
                task = {
                    'account': account_id,
                    'video_id': video_id,
                    'title': vdata.get('judul', ''),
                    'actions': list(set(actions)),
                    'priority': priority,
                    'metrics': {
                        'views': views,
                        'likes': likes,
                        'ctr': round(ctr, 4),
                        'retention': round(retention, 4),
                        'engagement': round(engagement, 4),
                    },
                    'created_at': today.strftime('%Y-%m-%d'),
                }
                new_tasks.append(task)
                print(f"  [OPT] {video_id}: {', '.join(actions)} ({priority})")

    # Save
    opt_queue['tasks'] = new_tasks
    opt_queue['generated_at'] = today.strftime('%Y-%m-%d %H:%M')
    _save_json(OPT_QUEUE_FILE, opt_queue)
    _save_json(PATTERNS_FILE, patterns)

    print(f"\n=== {len(new_tasks)} optimization tasks queued ===")


if __name__ == "__main__":
    analyze_performance()
