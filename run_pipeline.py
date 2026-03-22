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
    
    # V1: Data Prep (validate → inspect → extract → storyboard)
    # Engine reads stock from git checkout — produk.csv + images/ committed by collector
    # NO collector call here — engine is 100% independent from collector
    v1_steps = [
        "python engine/modules/product_validator.py",
        # AI Vision: inspect + score downloaded images (auto-detect category per image)
        "python engine/modules/cf_vision_inspector.py --image engine/data/images",
        "python engine/modules/extract_masalah.py",
        "python engine/modules/generate_storyboard.py"
    ]

    # DATA CHECKPOINT: warn if produk.csv has no products
    # NOT fatal — pipeline will catch 0-video at end and exit with proper message
    v1_checkpoint = {
        'file': 'engine/data/produk.csv',
        'min_lines': 2,  # header + at least 1 product
        'msg': 'Stok produk kosong — jalankan Product Collector untuk menambah stok.',
        'fatal': False,
    }
    
    # V2: Batch Manager (select products → assign to accounts → random schedule)
    v2_steps = [
        "python engine/modules/batch_manager.py"
    ]
    slot_arg = None
    if len(sys.argv) > 2:
        slot_arg = sys.argv[2]
        if slot_arg in ['pagi', 'siang', 'sore', 'malam']:
            v2_steps[0] += f" --slot {slot_arg}"
    
    # V3: Hook Selection & Variation (per YT and TT queue)
    v3_steps = [
        "python engine/modules/hook_selector.py",
        "python engine/modules/hook_variant_generator.py"
    ]
    
    # V4: CTA Selection & Variation (per YT and TT queue)
    v4_steps = [
        "python engine/modules/cta_selector.py",
        "python engine/modules/cta_variant_generator.py",
        # AI Copywriter: generate unique hooks, CTAs, descriptions
        "python engine/modules/cf_copywriter.py --queue engine/queue/storyboard_queue.jsonl",
    ]
    
    # V5: Video Production Pipeline
    # Jika QC mode (SKIP_YT_UPLOAD=true) → SELALU generate video, tidak peduli slot
    # Jika production → pagi/sore = render ALL, siang/malam = skip
    skip_upload = os.environ.get('SKIP_YT_UPLOAD', '').lower() == 'true'
    is_long_slot = slot_arg in ('pagi', 'sore')
    is_short_slot = slot_arg in ('siang', 'malam')
    force_render = skip_upload  # QC mode = selalu render untuk review
    
    v5_steps = [
        # Pre-production: Fonts + SFX cache + backgrounds (photos + videos) + music library
        "python engine/modules/font_helper.py",
        "python engine/modules/sound_manager.py",
        "python engine/modules/music_downloader.py",
        # Visual pipeline: composite product images → enhance/beautify
        "python engine/modules/image_enhancer.py",
        "python engine/modules/image_compositor.py",
        # Beautify all composites (local PIL + CF SD img2img)
        "python engine/modules/cf_image_enhancer.py --input engine/data/composites",
        # Deduplication + planning
        "python engine/modules/dedup_tracker.py",
        "python engine/modules/micro_cut_planner.py",
        "python engine/modules/body_micro_editor.py",
        # Pre-rendering QC
        "python engine/modules/body_retention_evaluator.py",
        # Generate per-video music (unique track per video)
        "python engine/modules/generate_music.py",
        # CLEANUP: wipe ALL old voiceover files to prevent stale theme/scene bleed
        "python -c \"import os, glob; [os.remove(f) for f in glob.glob('engine/data/voiceovers/**/vo_*.mp3', recursive=True)]\"",
        # AI TTS: generate voiceover per PLATFORM queue (each has correct account_id)
        # YT queue → yt_short + yt_long VOs (account_id = yt_1..yt_5)
        "python engine/modules/tts_voiceover.py --queue engine/queue/yt_queue.jsonl --platform yt",
        # TT queue → tt VOs (account_id = tt_1)
        "python engine/modules/tts_voiceover.py --queue engine/queue/tt_queue.jsonl --platform tt",
        # FB queue → fb VOs (account_id = fb_1)
        "python engine/modules/tts_voiceover.py --queue engine/queue/fb_queue.jsonl --platform fb",
    ]
    
    if is_long_slot or force_render:
        # ── PRODUCTION or QC MODE: render ALL ──
        if force_render and not is_long_slot:
            print(f"[QC MODE] Slot={slot_arg} tapi force render karena SKIP_YT_UPLOAD=true")
        v5_steps.extend([
            # YouTube: Long-form + auto-extract Shorts
            "python engine/modules/generate_video_yt_long.py",
            "python engine/modules/generate_video_yt_short.py",
            # TikTok + Facebook: generated here too
            "python engine/modules/generate_video_tt.py",
            "python engine/modules/generate_video_fb.py",
        ])
    # Short slots (production only): skip ALL video rendering
    # YT Shorts already uploaded with scheduled time by Long slot
    # TT+FB already emailed from Long slot
    
    v5_steps.extend([
        # Post-render: color grading per category
        "python engine/modules/color_grading.py",
        # Post-render QC (handles empty gracefully)
        "python engine/modules/body_drop_detector.py",
        "python engine/modules/qc_engine.py",
        # Metadata (Gemini-powered + legacy)
        "python engine/modules/metadata_generator.py",
        "python engine/modules/generate_yt_metadata.py",
        "python engine/modules/generate_fb_metadata.py",
        "python engine/modules/generate_ttfb_metadata.py",
        # Metrics tracking
        "python engine/modules/hook_metrics_collector.py",
        "python engine/modules/cta_metrics_collector.py",
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
    elif skip_upload:
        print("[QC MODE] YT upload DILEWATI — video disimpan di artifacts untuk review")

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
