"""
yt_performance_monitor.py
Collects performance data from YouTube Analytics API for all 5 accounts.
Runs bi-weekly (every 2 weeks, Monday morning).
Only analyzes videos older than 14 days.
"""
import os
import json
import datetime
import pickle
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')
CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
TOKENS_DIR = os.path.join(CONFIG_DIR, 'tokens')
PERF_FILE = os.path.join(STATE_DIR, 'performance_data.json')
MIN_AGE_DAYS = 14  # Don't analyze videos younger than 14 days


def _load_performance_data():
    """Load existing performance data."""
    if os.path.exists(PERF_FILE):
        with open(PERF_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_performance_data(data):
    """Save performance data."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PERF_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_yt_service(account_id):
    """Build YouTube Data API service for an account."""
    token_path = os.path.join(TOKENS_DIR, f'{account_id}.pickle')
    if not os.path.exists(token_path):
        print(f"  [SKIP] No token for {account_id}")
        return None, None

    with open(token_path, 'rb') as f:
        creds = pickle.load(f)

    yt_data = build('youtube', 'v3', credentials=creds)

    # Try to build Analytics service (may not be available)
    try:
        yt_analytics = build('youtubeAnalytics', 'v2', credentials=creds)
    except Exception:
        yt_analytics = None

    return yt_data, yt_analytics


def _get_channel_videos(yt_data, max_results=50):
    """Get list of uploaded videos for a channel."""
    try:
        # Get channel's upload playlist
        ch_resp = yt_data.channels().list(part='contentDetails', mine=True).execute()
        if not ch_resp.get('items'):
            return []
        
        uploads_id = ch_resp['items'][0]['contentDetails']['relatedPlaylists']['uploads']

        videos = []
        next_page = None
        while len(videos) < max_results:
            pl_resp = yt_data.playlistItems().list(
                part='snippet',
                playlistId=uploads_id,
                maxResults=min(50, max_results - len(videos)),
                pageToken=next_page
            ).execute()

            for item in pl_resp.get('items', []):
                vid_id = item['snippet']['resourceId']['videoId']
                pub_date = item['snippet']['publishedAt'][:10]
                title = item['snippet']['title']
                videos.append({
                    'video_id': vid_id,
                    'title': title,
                    'published': pub_date,
                })

            next_page = pl_resp.get('nextPageToken')
            if not next_page:
                break

        return videos
    except Exception as e:
        print(f"  [WARN] Failed to get videos: {e}")
        return []


def _get_video_stats(yt_data, video_ids):
    """Get basic stats for videos via Data API."""
    stats = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        try:
            resp = yt_data.videos().list(
                part='statistics,contentDetails',
                id=','.join(batch)
            ).execute()
            for item in resp.get('items', []):
                vid_id = item['id']
                s = item.get('statistics', {})
                stats[vid_id] = {
                    'views': int(s.get('viewCount', 0)),
                    'likes': int(s.get('likeCount', 0)),
                    'comments': int(s.get('commentCount', 0)),
                }
        except Exception as e:
            print(f"  [WARN] Stats fetch failed: {e}")
    return stats


def _get_analytics_data(yt_analytics, video_id, start_date, end_date):
    """Get watch time and CTR from Analytics API."""
    if not yt_analytics:
        return {}
    try:
        resp = yt_analytics.reports().query(
            ids='channel==MINE',
            startDate=start_date,
            endDate=end_date,
            metrics='views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage',
            filters=f'video=={video_id}',
        ).execute()

        rows = resp.get('rows', [])
        if rows:
            row = rows[0]
            return {
                'views': int(row[0]),
                'watch_time_minutes': float(row[1]),
                'avg_view_duration': float(row[2]),
                'retention_rate': float(row[3]) / 100.0,
            }
    except Exception as e:
        print(f"  [WARN] Analytics failed for {video_id}: {e}")
    return {}


def collect_performance(accounts=None):
    """Collect performance data for all YouTube accounts."""
    print("=== YT Performance Monitor ===")

    if accounts is None:
        accounts = ['yt_1', 'yt_2', 'yt_3', 'yt_4', 'yt_5']

    data = _load_performance_data()
    today = datetime.datetime.now()
    week_key = f"minggu_{today.isocalendar()[1]}"
    cutoff = today - datetime.timedelta(days=MIN_AGE_DAYS)

    for acct in accounts:
        print(f"\n  📊 Account: {acct}")
        yt_data, yt_analytics = _get_yt_service(acct)
        if not yt_data:
            continue

        if acct not in data:
            data[acct] = {}

        # Get all videos
        videos = _get_channel_videos(yt_data)
        print(f"  Found {len(videos)} videos")

        # Filter: only videos older than 14 days
        eligible = []
        for v in videos:
            pub_date = datetime.datetime.strptime(v['published'], '%Y-%m-%d')
            if pub_date < cutoff:
                eligible.append(v)

        print(f"  Eligible (>{MIN_AGE_DAYS} days old): {len(eligible)}")

        if not eligible:
            continue

        # Get stats
        vid_ids = [v['video_id'] for v in eligible]
        stats = _get_video_stats(yt_data, vid_ids)

        # Store data
        for v in eligible:
            vid_id = v['video_id']
            if vid_id not in data[acct]:
                data[acct][vid_id] = {
                    'judul': v['title'],
                    'tanggal_upload': v['published'],
                    'kategori': '',
                }

            # Add weekly data point
            week_data = stats.get(vid_id, {})

            # Try analytics if available
            start = (today - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
            end = today.strftime('%Y-%m-%d')
            analytics = _get_analytics_data(yt_analytics, vid_id, start, end)
            week_data.update(analytics)

            data[acct][vid_id][week_key] = week_data

        print(f"  [OK] Collected data for {len(eligible)} videos")

    _save_performance_data(data)
    print(f"\n=== Performance data saved ===")


if __name__ == "__main__":
    collect_performance()
