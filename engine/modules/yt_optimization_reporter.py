"""
yt_optimization_reporter.py
Generates weekly performance report HTML and sends via email.
Runs after yt_content_optimizer.py completes.
"""
import os
import json
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

STATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'state')
PERF_FILE = os.path.join(STATE_DIR, 'performance_data.json')
PATTERNS_FILE = os.path.join(STATE_DIR, 'success_patterns.json')
OPT_QUEUE_FILE = os.path.join(STATE_DIR, 'optimization_queue.json')


def _load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def generate_report():
    """Generate HTML performance report."""
    print("=== YT Optimization Reporter ===")

    perf_data = _load_json(PERF_FILE)
    patterns = _load_json(PATTERNS_FILE)
    opt_queue = _load_json(OPT_QUEUE_FILE)

    today = datetime.datetime.now()
    week = today.isocalendar()[1]

    html = f"""
    <html>
    <head>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px;
                      border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 10px; }}
        h2 {{ color: #16213e; margin-top: 30px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th {{ background: #16213e; color: white; padding: 10px; text-align: left; }}
        td {{ padding: 8px 10px; border-bottom: 1px solid #eee; }}
        tr:nth-child(even) {{ background: #f9f9f9; }}
        .good {{ color: #28a745; font-weight: bold; }}
        .warn {{ color: #ffc107; font-weight: bold; }}
        .bad {{ color: #dc3545; font-weight: bold; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 10px;
                  font-size: 11px; font-weight: bold; }}
        .badge-high {{ background: #fde2e2; color: #dc3545; }}
        .badge-medium {{ background: #fff3cd; color: #856404; }}
        .badge-success {{ background: #d4edda; color: #155724; }}
    </style>
    </head>
    <body>
    <div class='container'>
        <h1>📊 Laporan Performa YouTube — Minggu {week}</h1>
        <p>Tanggal: {today.strftime('%d %B %Y')}</p>
    """

    # === Per Account Summary ===
    for account_id in sorted(perf_data.keys()):
        videos = perf_data[account_id]
        total_views = 0
        total_likes = 0
        video_count = len(videos)

        for vid_id, vdata in videos.items():
            weeks = sorted([k for k in vdata.keys() if k.startswith('minggu_')])
            if weeks:
                latest = vdata.get(weeks[-1], {})
                total_views += latest.get('views', 0)
                total_likes += latest.get('likes', 0)

        html += f"""
        <h2>🎬 {account_id.upper()} — {video_count} videos</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total Views (week)</td><td>{total_views:,}</td></tr>
            <tr><td>Total Likes (week)</td><td>{total_likes:,}</td></tr>
            <tr><td>Videos Tracked</td><td>{video_count}</td></tr>
        </table>
        """

        # Top 5 videos
        top = sorted(videos.items(),
                     key=lambda x: x[1].get(sorted([k for k in x[1] if k.startswith('minggu_')])[-1] if [k for k in x[1] if k.startswith('minggu_')] else 'x', {}).get('views', 0),
                     reverse=True)[:5]

        if top:
            html += "<h3>Top 5 Videos</h3><table><tr><th>Video</th><th>Views</th><th>Likes</th></tr>"
            for vid_id, vdata in top:
                title = vdata.get('judul', vid_id)[:40]
                weeks = sorted([k for k in vdata if k.startswith('minggu_')])
                latest = vdata.get(weeks[-1], {}) if weeks else {}
                html += f"<tr><td>{title}</td><td>{latest.get('views',0):,}</td><td>{latest.get('likes',0):,}</td></tr>"
            html += "</table>"

    # === Optimizations Performed ===
    executed_at = opt_queue.get('executed_at', '')
    if executed_at:
        html += f"""
        <h2>🔧 Optimasi yang Dilakukan</h2>
        <p>Terakhir dieksekusi: {executed_at}</p>
        """

    # === Success Patterns ===
    success_list = patterns.get('success_patterns', [])
    if success_list:
        html += f"""
        <h2>🏆 Video Performa Terbaik (CTR>6%, Retention>50%)</h2>
        <table><tr><th>Account</th><th>Video</th><th>CTR</th><th>Retention</th></tr>
        """
        for p in success_list[-10:]:
            html += f"""<tr>
                <td>{p.get('account','')}</td>
                <td>{p.get('title','')[:35]}</td>
                <td class='good'>{p.get('ctr',0):.1%}</td>
                <td class='good'>{p.get('retention',0):.1%}</td>
            </tr>"""
        html += "</table>"

    html += """
    <hr style='margin-top:30px'>
    <p style='color:#666; font-size:12px;'>Auto-generated by YT Optimization Reporter</p>
    </div></body></html>
    """

    # Save report
    report_path = os.path.join(STATE_DIR, f'report_week{week}.html')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  [OK] Report saved: {report_path}")

    # Send via email
    _send_report_email(html, week)

    return report_path


def _send_report_email(html_content, week):
    """Send report via email."""
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASS', '')
    notify_email = os.environ.get('NOTIFY_EMAIL', '')

    if not all([smtp_user, smtp_pass, notify_email]):
        print("  [SKIP] Email credentials not configured")
        return

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'📊 Laporan Performa YouTube — Minggu {week}'
        msg['From'] = smtp_user
        msg['To'] = notify_email
        msg.attach(MIMEText(html_content, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, notify_email, msg.as_string())
        print(f"  [OK] Report emailed to {notify_email}")
    except Exception as e:
        print(f"  [WARN] Email failed: {e}")


if __name__ == "__main__":
    generate_report()
