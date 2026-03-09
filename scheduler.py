"""
scheduler.py
Automated scheduler yang menjalankan pipeline di 3 slot waktu per hari:
  - Pagi:  random antara 06:00-09:00
  - Sore:  random antara 14:00-17:00
  - Malam: random antara 19:00-22:00

Setiap slot memproses 1 produk yang berbeda, menghasilkan:
  - 5 video YouTube unik (1 per akun)
  - 1 video TikTok
  - Upload otomatis ke YouTube
  - TikTok disimpan untuk posting manual

Usage:
  python scheduler.py              # Jalankan daemon (terus menerus)
  python scheduler.py --once       # Jalankan 1x untuk slot saat ini
  python scheduler.py --slot pagi  # Paksa jalankan slot tertentu
"""
import os
import sys
import random
import datetime
import time
import subprocess
import yaml
import argparse


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "engine", "config", "engine_config.yaml")
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def random_time_in_range(start_str, end_str):
    """Generate random HH:MM within range."""
    sh, sm = map(int, start_str.split(':'))
    eh, em = map(int, end_str.split(':'))
    start_min = sh * 60 + sm
    end_min = eh * 60 + em
    rand_min = random.randint(start_min, end_min)
    return f"{rand_min // 60:02d}:{rand_min % 60:02d}"


def get_current_slot(config):
    """Determine which slot the current time falls into."""
    now = datetime.datetime.now()
    current_minutes = now.hour * 60 + now.minute
    
    slots = config['schedule']['slots']
    for slot_name, slot_cfg in slots.items():
        r = slot_cfg['range']
        sh, sm = map(int, r[0].split(':'))
        eh, em = map(int, r[1].split(':'))
        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        if start_min <= current_minutes <= end_min:
            return slot_name
    return None


def run_pipeline_for_slot(slot):
    """Run the full pipeline for a specific time slot."""
    print(f"\n{'='*60}")
    print(f"SCHEDULER: Running pipeline for slot '{slot}'")
    print(f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    project_dir = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    
    # Run full pipeline with the slot parameter
    cmd = f"python run_pipeline.py full {slot}"
    result = subprocess.run(cmd, shell=True, cwd=project_dir, env=env)
    
    if result.returncode == 0:
        print(f"\n[OK] Pipeline for slot '{slot}' completed successfully!")
        return True
    else:
        print(f"\n[FAIL] Pipeline for slot '{slot}' failed with exit code {result.returncode}")
        return False


def run_monitoring():
    """Run YouTube monitoring and optimization pipeline (Bagian 9).
    Runs bi-weekly: monitor -> analyzer -> optimizer -> reporter."""
    print(f"\n{'='*60}")
    print(f"SCHEDULER: Running YouTube Monitoring & Optimization")
    print(f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    project_dir = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'

    monitor_steps = [
        ("yt_performance_monitor.py", "Collecting YouTube Analytics data"),
        ("yt_performance_analyzer.py", "Analyzing performance & building optimization queue"),
        ("yt_content_optimizer.py", "Executing optimizations via YouTube Data API"),
        ("yt_optimization_reporter.py", "Generating and sending report"),
    ]

    for module, desc in monitor_steps:
        print(f"\n--- {desc} ---")
        module_path = os.path.join("engine", "modules", module)
        if not os.path.exists(os.path.join(project_dir, module_path)):
            print(f"  [SKIP] {module} not found")
            continue

        result = subprocess.run(
            f"python {module_path}", shell=True, cwd=project_dir, env=env
        )
        if result.returncode != 0:
            print(f"  [WARN] {module} exited with code {result.returncode}")
        else:
            print(f"  [OK] {module} completed")

    print(f"\n[OK] Monitoring pipeline completed!")
    return True


def is_monitoring_week():
    """Check if this is a monitoring week (bi-weekly, even ISO weeks)."""
    iso_week = datetime.datetime.now().isocalendar()[1]
    return iso_week % 2 == 0


def schedule_daily(config):
    """Schedule pipelines for pagi, sore, malam with random times each day."""
    try:
        import schedule as sched_lib
    except ImportError:
        print("Error: 'schedule' library not installed.")
        print("Run: pip install schedule")
        sys.exit(1)
    
    slots = config['schedule']['slots']
    
    def schedule_today():
        """Generate random times for today and schedule them."""
        sched_lib.clear()
        
        print(f"\n{'='*60}")
        print(f"SCHEDULER: Planning today's schedule")
        print(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}")
        print(f"{'='*60}")
        
        for slot_name, slot_cfg in slots.items():
            r = slot_cfg['range']
            run_time = random_time_in_range(r[0], r[1])
            print(f"  {slot_name}: scheduled at {run_time} (range {r[0]}-{r[1]})")
            sched_lib.every().day.at(run_time).do(run_pipeline_for_slot, slot_name).tag(slot_name)
        
        # Re-schedule for tomorrow at 00:01
        sched_lib.every().day.at("00:01").do(schedule_today).tag("reschedule")
        print(f"\nWaiting for scheduled times...\n")
    
    schedule_today()
    
    print("Scheduler daemon started. Press Ctrl+C to stop.\n")
    try:
        while True:
            sched_lib.run_pending()
            time.sleep(30)  # Check every 30 seconds
    except KeyboardInterrupt:
        print("\nScheduler stopped.")


def main():
    parser = argparse.ArgumentParser(description="Video Engine Scheduler")
    parser.add_argument('--once', action='store_true', 
                       help='Run once for the current time slot, then exit')
    parser.add_argument('--slot', choices=['pagi', 'sore', 'malam'],
                       help='Force run a specific slot')
    parser.add_argument('--monitor', action='store_true',
                       help='Run YouTube monitoring & optimization pipeline')
    parser.add_argument('--daemon', action='store_true',
                       help='Run as daemon with auto-scheduling (default)')
    args = parser.parse_args()
    
    config = load_config()
    
    if args.monitor:
        # Run monitoring pipeline (Bagian 9)
        if is_monitoring_week():
            print("This is a monitoring week. Running optimization pipeline...")
            success = run_monitoring()
        else:
            print("Not a monitoring week (bi-weekly schedule). Skipping.")
            success = True
        sys.exit(0 if success else 1)
    
    elif args.slot:
        # Force run a specific slot
        print(f"Force-running slot: {args.slot}")
        success = run_pipeline_for_slot(args.slot)
        sys.exit(0 if success else 1)
    
    elif args.once:
        # Run for current time slot
        slot = get_current_slot(config)
        if slot:
            print(f"Current time matches slot: {slot}")
            # On monitoring weeks, run monitoring before pipeline (Monday)
            if is_monitoring_week() and datetime.datetime.now().weekday() == 0:
                print("Monday + monitoring week: running optimization first...")
                run_monitoring()
            success = run_pipeline_for_slot(slot)
            sys.exit(0 if success else 1)
        else:
            print(f"No time slot active right now ({datetime.datetime.now().strftime('%H:%M')})")
            print("Available slots:")
            for name, cfg in config['schedule']['slots'].items():
                r = cfg['range']
                print(f"  {name}: {r[0]} - {r[1]}")
            sys.exit(0)
    
    else:
        # Default: daemon mode
        schedule_daily(config)


if __name__ == "__main__":
    main()
