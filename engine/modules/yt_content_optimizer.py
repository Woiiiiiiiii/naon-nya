"""
yt_content_optimizer.py
Executes optimization actions from optimization_queue.json.
Updates title, description, tags, and thumbnail via YouTube Data API.
Uses Gemini for generating improved titles/descriptions.
"""
import os
import json
import pickle
import datetime
from googleapiclient.discovery import build

STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')
CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
TOKENS_DIR = os.path.join(CONFIG_DIR, 'tokens')
OPT_QUEUE_FILE = os.path.join(STATE_DIR, 'optimization_queue.json')
PERF_FILE = os.path.join(STATE_DIR, 'performance_data.json')
PATTERNS_FILE = os.path.join(STATE_DIR, 'success_patterns.json')


def _get_yt_service(account_id):
    """Build YouTube Data API service."""
    token_path = os.path.join(TOKENS_DIR, f'{account_id}.pickle')
    if not os.path.exists(token_path):
        return None
    with open(token_path, 'rb') as f:
        creds = pickle.load(f)
    return build('youtube', 'v3', credentials=creds)


def _optimize_title(yt, video_id, old_title, metrics, category):
    """Generate and update improved title via Gemini + YouTube API."""
    from metadata_generator import call_gemini

    patterns = {}
    if os.path.exists(PATTERNS_FILE):
        with open(PATTERNS_FILE, 'r') as f:
            patterns = json.load(f)

    # Get success pattern titles for reference
    ref_titles = []
    for p in patterns.get('success_patterns', []):
        if p.get('kategori') == category:
            ref_titles.append(p.get('title', ''))

    prompt = f"""Perbaiki judul video YouTube ini agar lebih clickable.

Judul lama: {old_title}
Performa: Views={metrics.get('views',0)}, CTR={metrics.get('ctr',0):.2%}
Kategori: {category}
{'Referensi judul sukses: ' + ', '.join(ref_titles[:3]) if ref_titles else ''}

Buat 1 judul baru yang lebih menarik, max 60 karakter.
Berikan HANYA judul, tanpa penjelasan."""

    new_title = call_gemini(prompt)
    if not new_title:
        return False

    new_title = new_title.strip('"\'').split('\n')[0][:60]

    try:
        # Get current video snippet
        resp = yt.videos().list(part='snippet', id=video_id).execute()
        if not resp.get('items'):
            return False
        snippet = resp['items'][0]['snippet']
        snippet['title'] = new_title

        yt.videos().update(
            part='snippet',
            body={'id': video_id, 'snippet': snippet}
        ).execute()
        print(f"    [OK] Title updated: {new_title}")
        return True
    except Exception as e:
        print(f"    [FAIL] Title update: {e}")
        return False


def _optimize_description(yt, video_id, metrics, category):
    """Generate and update improved description."""
    from metadata_generator import call_gemini

    prompt = f"""Perbaiki deskripsi video YouTube untuk meningkatkan retention.
Kategori: {category}
Views saat ini: {metrics.get('views',0)}
Retention: {metrics.get('retention',0):.0%}

Buat deskripsi baru yang:
- Kaya keyword untuk SEO
- CTA yang kuat (link di komentar pertama)
- Informatif tentang produk
- Max 2000 karakter

Berikan HANYA deskripsi, tanpa penjelasan."""

    new_desc = call_gemini(prompt)
    if not new_desc:
        return False

    try:
        resp = yt.videos().list(part='snippet', id=video_id).execute()
        if not resp.get('items'):
            return False
        snippet = resp['items'][0]['snippet']
        snippet['description'] = new_desc

        yt.videos().update(
            part='snippet',
            body={'id': video_id, 'snippet': snippet}
        ).execute()
        print(f"    [OK] Description updated")
        return True
    except Exception as e:
        print(f"    [FAIL] Description update: {e}")
        return False


def _optimize_tags(yt, video_id, category, expand=False):
    """Generate and update improved tags."""
    from metadata_generator import call_gemini

    action = "Perluas" if expand else "Perbaiki"
    prompt = f"""{action} tags YouTube untuk kategori {category}.
Buat 15-20 tag yang relevan, mix Bahasa Indonesia dan English.
Include long-tail keyword.
Format: tag1, tag2, tag3, ...
Berikan HANYA tags, tanpa penjelasan."""

    result = call_gemini(prompt)
    if not result:
        return False

    tags = [t.strip() for t in result.split(',') if t.strip()][:20]

    try:
        resp = yt.videos().list(part='snippet', id=video_id).execute()
        if not resp.get('items'):
            return False
        snippet = resp['items'][0]['snippet']
        snippet['tags'] = tags

        yt.videos().update(
            part='snippet',
            body={'id': video_id, 'snippet': snippet}
        ).execute()
        print(f"    [OK] Tags updated ({len(tags)} tags)")
        return True
    except Exception as e:
        print(f"    [FAIL] Tags update: {e}")
        return False


def execute_optimizations():
    """Execute all queued optimizations."""
    print("=== YT Content Optimizer ===")

    if not os.path.exists(OPT_QUEUE_FILE):
        print("  No optimization queue found")
        return

    with open(OPT_QUEUE_FILE, 'r') as f:
        queue = json.load(f)

    tasks = queue.get('tasks', [])
    if not tasks:
        print("  No tasks in queue")
        return

    # Sort by priority
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    tasks.sort(key=lambda t: priority_order.get(t.get('priority', 'low'), 2))

    perf_data = {}
    if os.path.exists(PERF_FILE):
        with open(PERF_FILE, 'r') as f:
            perf_data = json.load(f)

    optimized = 0
    for task in tasks:
        account = task['account']
        video_id = task['video_id']
        actions = task['actions']
        metrics = task['metrics']
        title = task.get('title', '')

        print(f"\n  🔧 {account}/{video_id}: {', '.join(actions)}")

        yt = _get_yt_service(account)
        if not yt:
            print(f"    [SKIP] No API access for {account}")
            continue

        category = ''
        if account in perf_data and video_id in perf_data[account]:
            category = perf_data[account][video_id].get('kategori', '')

        success = False
        for action in actions:
            if action == 'optimize_title':
                success |= _optimize_title(yt, video_id, title, metrics, category)
            elif action == 'optimize_description' or action == 'strengthen_cta':
                success |= _optimize_description(yt, video_id, metrics, category)
            elif action in ('optimize_tags', 'expand_tags'):
                success |= _optimize_tags(yt, video_id, category,
                                          expand=(action == 'expand_tags'))
            elif action == 'full_refresh':
                _optimize_title(yt, video_id, title, metrics, category)
                _optimize_description(yt, video_id, metrics, category)
                _optimize_tags(yt, video_id, category)
                success = True

        if success:
            # Mark as optimized
            if account in perf_data and video_id in perf_data[account]:
                perf_data[account][video_id]['last_optimized'] = \
                    datetime.datetime.now().strftime('%Y-%m-%d')
            optimized += 1

    # Save updated perf data
    with open(PERF_FILE, 'w', encoding='utf-8') as f:
        json.dump(perf_data, f, ensure_ascii=False, indent=2)

    # Clear completed queue
    queue['tasks'] = []
    queue['executed_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    with open(OPT_QUEUE_FILE, 'w') as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

    print(f"\n=== Optimized {optimized}/{len(tasks)} videos ===")


if __name__ == "__main__":
    execute_optimizations()
