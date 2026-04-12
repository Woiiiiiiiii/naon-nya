import subprocess
import sys
import os
import time
import glob

STEP_TIMEOUT = 3600  # 60 minutes max per step (4 video generators + data prep need time)

def run_step(command, critical=False):
    """Run a pipeline step. Returns True if succeeded.
    Non-critical steps log errors and continue. Critical steps halt pipeline."""
    print(f"\n>>> Running: {command}")
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    try:
        result = subprocess.run(command, shell=True, env=env, timeout=STEP_TIMEOUT)
        if result.returncode != 0:
            print(f"!!! Error in step: {command} (exit code {result.returncode})")
            if critical:
                print("[FAIL] Critical step failed -> STOP")
                return False
            print("[WARN] Non-critical step failed, continuing...")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"!!! TIMEOUT ({STEP_TIMEOUT}s) in step: {command}")
        print("[WARN] Step timed out, continuing...")
        return False
    except Exception as e:
        print(f"!!! Exception in step: {command} -> {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_pipeline.py [v1|v2|v3|v4|v5|full]")
        sys.exit(1)
        
    mode = sys.argv[1].lower()
    
    # V1: Data Prep — REMOVED
    # batch_manager.py now reads produk.csv directly,
    # validates image inline (1 per category), retries on QC failure.
    # No need to validate/inspect/storyboard ALL 270 products.
    v1_steps = []

    # DATA CHECKPOINT: warn if produk.csv has no products
    v1_checkpoint = {
        'file': 'engine/data/produk.csv',
        'min_lines': 2,  # header + at least 1 product
        'msg': 'Stok produk kosong — jalankan Product Collector untuk menambah stok.',
        'fatal': False,
    }
    
    # V2: Batch Manager (select 1 per category → validate image → generate storyboard inline)
    v2_steps = [
        "python engine/modules/batch_manager.py"
    ]
    slot_arg = None
    if len(sys.argv) > 2:
        slot_arg = sys.argv[2]
        if slot_arg in ['pagi', 'siang', 'sore', 'malam']:
            v2_steps[0] += f" --slot {slot_arg}"
    
    # V3: REMOVED — no more hook selection (slideshow format, no text overlay)
    v3_steps = []
    
    # V4: REMOVED — no more CTA/copywriter (slideshow format, no text overlay)
    v4_steps = []
    
    # V5: Video Production Pipeline
    # Jika QC mode (SKIP_YT_UPLOAD=true) → SELALU generate video, tidak peduli slot
    # Jika production → pagi/sore = render ALL, siang/malam = skip
    skip_upload = os.environ.get('SKIP_YT_UPLOAD', '').lower() == 'true'
    is_long_slot = slot_arg in ('pagi', 'sore')
    is_short_slot = slot_arg in ('siang', 'malam')
    force_render = skip_upload  # QC mode = selalu render untuk review
    
    v5_steps = [
        # Pre-production: Fonts + SFX cache
        "python engine/modules/font_helper.py",
        "python engine/modules/sound_manager.py",
        # Download 4 product images per product (original Shopee seller images)
        "python engine/modules/download_images.py --multi",
        # Deduplication tracking
        "python engine/modules/dedup_tracker.py",
        # Generate per-video background music
        "python engine/modules/generate_music.py",
    ]
    
    if is_long_slot or force_render:
        # ── PRODUCTION or QC MODE: render ALL platforms ──
        if force_render and not is_long_slot:
            print(f"[QC MODE] Slot={slot_arg} tapi force render karena SKIP_YT_UPLOAD=true")
        v5_steps.extend([
            # SLIDESHOW: single generator for ALL platforms (YT Long, YT Short, TT, FB)
            "python engine/modules/generate_video_slideshow.py",
        ])
    # Short slots (production only): skip ALL video rendering
    # YT Shorts already uploaded with scheduled time by Long slot
    # TT+FB already emailed from Long slot
    
    v5_steps.extend([
        # Post-render QC (handles empty gracefully)
        "python engine/modules/qc_engine.py",
        # Metadata (Gemini-powered + legacy)
        # NOTE: metadata_generator.py REMOVED from pipeline (2026-04-12)
        # Reason: its output ({produk_id}_gemini_meta.json) is NOT consumed
        # by any downstream module. generate_yt_metadata.py already calls
        # call_gemini() directly for YT-specific metadata. Running both
        # wastes ~14 Gemini API calls per run and triggers 429 rate limits
        # because they share the same per-channel API keys.
        # The call_gemini() function in metadata_generator.py is still
        # available as an import for other modules.
        "python engine/modules/generate_yt_metadata.py",
        "python engine/modules/generate_fb_metadata.py",
        "python engine/modules/generate_ttfb_metadata.py",
        # Generate pipeline report
        "python engine/modules/generate_report.py",
    ])
    
    skip_upload = os.environ.get('SKIP_YT_UPLOAD', '').lower() == 'true'

    if is_long_slot and not skip_upload:
        # Upload + cleanup only on production slots
        v5_steps.extend([
            # Upload YT (Long now + Shorts scheduled for siang/malam)
            "python engine/modules/youtube_upload.py",
            # Update Notion "link in bio" with today's product links
            "python engine/modules/notion_link_updater.py",
            # Cleanup YT
            "python engine/modules/delete_after_upload.py"
        ])

        # YT Maintenance: performance monitor + optimizer (sore slot only, bi-weekly)
        import datetime
        today = datetime.datetime.now()
        is_monday = today.weekday() == 0
        is_sore = slot_arg == 'sore'
        week_num = today.isocalendar()[1]
        is_biweekly = week_num % 2 == 0

        if is_sore and is_monday and is_biweekly:
            v5_steps.extend([
                # Collect performance data from YouTube Analytics
                "python engine/modules/yt_performance_monitor.py",
                # Analyze and optimize underperforming videos
                "python engine/modules/yt_performance_analyzer.py",
                # Execute optimizations (title, tags, description refresh)
                "python engine/modules/yt_content_optimizer.py",
            ])
            print("[MAINTENANCE] YT performance check + optimization scheduled")

    elif skip_upload:
        print("[QC MODE] YT upload DILEWATI -- video disimpan di artifacts untuk review")

    pipeline = []
    checkpoints = {}  # step_index -> checkpoint config
    if mode == "v1": pipeline = v1_steps
    elif mode == "v2": pipeline = v2_steps
    elif mode == "v3": pipeline = v3_steps
    elif mode == "v4": pipeline = v4_steps
    elif mode == "v5": pipeline = v5_steps
    elif mode == "full":
        pipeline = v1_steps + v2_steps + v3_steps + v4_steps + v5_steps
        # Data checkpoint after V1 (product scraping)
        checkpoints[len(v1_steps)] = v1_checkpoint
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)

    # Inject slot arg into report step
    if slot_arg and slot_arg in ['pagi', 'siang', 'sore', 'malam']:
        pipeline = [
            s + f" --slot {slot_arg}" if 'generate_report' in s else s
            for s in pipeline
        ]
        
    print(f"=== Pipeline Mode: {mode.upper()} ({len(pipeline)} steps) ===")
    passed = 0
    failed = 0
    failed_steps = []
    start_time = time.time()

    for i, step in enumerate(pipeline, 1):
        # CHECK: data checkpoint before this step?
        if (i - 1) in checkpoints:
            cp = checkpoints[i - 1]
            cp_file = cp['file']
            is_fatal = cp.get('fatal', True)
            if os.path.exists(cp_file):
                with open(cp_file, 'r') as f:
                    line_count = sum(1 for _ in f)
                if line_count < cp['min_lines']:
                    print(f"\n{'='*60}")
                    print(f"[{'HALT' if is_fatal else 'WARN'}] {cp['msg']}")
                    print(f"  File: {cp_file} has {line_count} lines (need >= {cp['min_lines']})")
                    if is_fatal:
                        sys.exit(1)
                    else:
                        print(f"  Continuing anyway — will catch at end if 0 videos produced")
            else:
                print(f"\n{'='*60}")
                print(f"[{'HALT' if is_fatal else 'WARN'}] Data file missing: {cp_file}")
                print(f"  {cp['msg']}")
                if is_fatal:
                    sys.exit(1)
                else:
                    print(f"  Continuing anyway — will catch at end if 0 videos produced")

        elapsed = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"Step {i}/{len(pipeline)} (elapsed: {int(elapsed)}s)")
        
        # All steps are non-critical — pipeline continues on failure
        # Video engine depends on STOCK (produk.csv + images), not on collector
        if run_step(step, critical=False):
            passed += 1
        else:
            failed += 1
            failed_steps.append(step.split('/')[-1].replace('.py', ''))
    
    # POST-PIPELINE: cleanup used product images to save storage
    try:
        sys.path.insert(0, 'engine/modules')
        from dedup_tracker import cleanup_used_images
        cleanup_used_images()
    except Exception as e:
        print(f"[WARN] Dedup cleanup failed: {e}")

    # COUNT OUTPUT: exit(1) if pipeline ran fully but produced 0 videos
    video_count = len(glob.glob('engine/output/**/*.mp4', recursive=True))
    
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"=== Pipeline {mode.upper()} complete ===")
    print(f"  Passed: {passed}/{passed+failed}")
    print(f"  Failed: {failed} {failed_steps if failed_steps else ''}")
    print(f"  Videos: {video_count}")
    print(f"  Duration: {int(elapsed)}s ({int(elapsed/60)}m)")
    
    if video_count == 0 and mode == 'full':
        print(f"\n[FAIL] Pipeline completed but produced 0 videos!")
        print(f"  Check scraper logs above for tier failure details.")
        sys.exit(1)
    
    if failed > 0:
        print(f"\n[WARN] {failed} step(s) failed but pipeline continued")

if __name__ == "__main__":
    main()
