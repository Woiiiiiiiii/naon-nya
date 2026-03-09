import subprocess
import sys
import os
import time

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
    
    # V1: Data Prep (bank export → scrape → validate → download images → extract → storyboard)
    v1_steps = [
        "python engine/modules/product_collector.py --export",   # Load from pre-collected bank FIRST
        "python engine/modules/scrape_produk.py",                # Scrape to fill gaps
        "python engine/modules/product_validator.py",
        "python engine/modules/download_images.py",
        # AI Vision: inspect + score downloaded images
        "python engine/modules/cf_vision_inspector.py --image engine/data/images --category home",
        "python engine/modules/extract_masalah.py",
        "python engine/modules/generate_storyboard.py"
    ]
    
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
        "python engine/modules/cf_image_enhancer.py --input engine/data/composites --category home",
        # Deduplication + planning
        "python engine/modules/dedup_tracker.py",
        "python engine/modules/micro_cut_planner.py",
        "python engine/modules/body_micro_editor.py",
        # Pre-rendering QC
        "python engine/modules/body_retention_evaluator.py",
        # Generate per-video music (unique track per video)
        "python engine/modules/generate_music.py",
        # AI TTS: generate voiceover for all products (per platform)
        "python engine/modules/tts_voiceover.py --queue engine/queue/storyboard_queue.jsonl --platform yt_short",
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
    if mode == "v1": pipeline = v1_steps
    elif mode == "v2": pipeline = v2_steps
    elif mode == "v3": pipeline = v3_steps
    elif mode == "v4": pipeline = v4_steps
    elif mode == "v5": pipeline = v5_steps
    elif mode == "full":
        pipeline = v1_steps + v2_steps + v3_steps + v4_steps + v5_steps
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
        elapsed = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"Step {i}/{len(pipeline)} (elapsed: {int(elapsed)}s)")
        
        # Only scrape_produk is critical — product_collector export can fail if bank empty
        is_critical = ('scrape_produk' in step)
        
        if run_step(step, critical=is_critical):
            passed += 1
        else:
            failed += 1
            failed_steps.append(step.split('/')[-1].replace('.py', ''))
            if is_critical:
                print("[HALT] Critical step failed, aborting pipeline")
                break
    
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"=== Pipeline {mode.upper()} complete ===")
    print(f"  Passed: {passed}/{passed+failed}")
    print(f"  Failed: {failed} {failed_steps if failed_steps else ''}")
    print(f"  Duration: {int(elapsed)}s ({int(elapsed/60)}m)")
    
    if failed > 0:
        print(f"\n[WARN] {failed} step(s) failed but pipeline continued")

if __name__ == "__main__":
    main()
