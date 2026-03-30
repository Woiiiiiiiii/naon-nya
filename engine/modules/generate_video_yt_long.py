"""
generate_video_yt_long.py
YouTube Long-form: 90-120s DETAILED product review.

Architecture (per instruksi_upgrade_system.md Bagian 5):
  Uses PRE-COMPOSITED images (product + photo background) from image_compositor.py
  7 scenes, each using a different composite image animated with Ken Burns + parallax.
  Text overlays + SFX on top.

7 Scenes:
  Hook(0-8s) -> Overview(8-25s) -> Detail1(25-45s) -> Detail2(45-65s)
  -> Comparison(65-80s) -> Verdict(80-95s) -> CTA(95-110s)

After rendering Long, AUTO-EXTRACTS a 45-50s Shorts version.
"""
import json
import os
import sys
import random
import datetime
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from moviepy import (VideoClip, ImageClip, AudioFileClip, CompositeAudioClip,
                     afx, concatenate_audioclips, concatenate_videoclips)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from engine.modules.category_router import (
    get_category, get_accent_color, get_copywriting,
    get_channel_name, VIDEO_DURATION
)
from engine.modules.video_effects import (
    render_text_image, paste_overlay_on_frame,
    text_slide_up, ease_out_back, ease_out_cubic,
    create_rating_stars, create_price_display, create_chat_bubble,
    create_count_up_text, create_blinking_label, create_simple_price,
    draw_frame_border, slide_element_x, sway_x,
    render_outline_text, create_plain_gradient
)
from engine.modules.sound_manager import get_sfx_path, init_sounds
from engine.modules.audio_normalizer import prepare_music, prepare_sfx, get_ffmpeg_audio_params, find_music_file, get_voice_volumes

W, H = 1080, 1920
COMPOSITES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'composites')

# Scene templates (3 variations for variety)
TEMPLATES = {
    'A': [
        {'id': 'hook',       's': 0,  'e': 8},
        {'id': 'overview',   's': 8,  'e': 25},
        {'id': 'detail1',    's': 25, 'e': 45},
        {'id': 'detail2',    's': 45, 'e': 65},
        {'id': 'comparison', 's': 65, 'e': 80},
        {'id': 'verdict',    's': 80, 'e': 95},
        {'id': 'cta',        's': 95, 'e': 110},
    ],
    'B': [
        {'id': 'hook',       's': 0,  'e': 6},
        {'id': 'overview',   's': 6,  'e': 20},
        {'id': 'detail1',    's': 20, 'e': 40},
        {'id': 'detail2',    's': 40, 'e': 60},
        {'id': 'comparison', 's': 60, 'e': 78},
        {'id': 'verdict',    's': 78, 'e': 92},
        {'id': 'cta',        's': 92, 'e': 110},
    ],
    'C': [
        {'id': 'hook',       's': 0,  'e': 10},
        {'id': 'overview',   's': 10, 'e': 28},
        {'id': 'detail1',    's': 28, 'e': 50},
        {'id': 'detail2',    's': 50, 'e': 68},
        {'id': 'comparison', 's': 68, 'e': 82},
        {'id': 'verdict',    's': 82, 'e': 96},
        {'id': 'cta',        's': 96, 'e': 115},
    ],
}


def _load_composites(produk_id, category='home', count=7):
    """Generate FRESH composite images every run.
    Deletes old cached composites to prevent duplicate content detection."""
    import glob

    # CLEANUP: delete old cached composites
    prod_dir = os.path.join(COMPOSITES_DIR, produk_id)
    if os.path.isdir(prod_dir):
        old = glob.glob(os.path.join(prod_dir, '*.png')) + glob.glob(os.path.join(prod_dir, '*.jpg'))
        for f in old:
            try: os.remove(f)
            except Exception: pass
    flat_old = glob.glob(os.path.join(COMPOSITES_DIR, f"{produk_id}_composite_*.png"))
    for f in flat_old:
        try: os.remove(f)
        except Exception: pass

    # ALWAYS generate fresh composites
    composites = _generate_fallback_composites(produk_id, category, count)

    # Ensure enough composites
    while len(composites) < count:
        idx = len(composites) % max(1, len(composites))
        composites.append(composites[idx].copy())

    # TRUE random shuffle (different order every run)
    random.shuffle(composites)

    return composites


def _generate_fallback_composites(produk_id, category, count=7):
    """Product on PREMIUM gradient background (glow + vignette + shadow)."""
    from engine.modules.premium_background import create_premium_background, add_product_shadow

    composites = []

    img_path = None
    for ext in ['png', 'jpg', 'webp']:
        p = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', f"{produk_id}.{ext}")
        if os.path.exists(p):
            img_path = p
            break

    product_img = None
    is_transparent = False
    if img_path:
        try:
            product_img = Image.open(img_path)
            if product_img.mode == 'RGBA':
                is_transparent = True
            else:
                product_img = product_img.convert('RGB')
            pw, ph = product_img.size
            if pw < 50 or ph < 50:
                product_img = None
        except Exception:
            product_img = None

    if product_img is None:
        print(f"    [WARN] No valid image for {produk_id}")
        variant_offset = random.randint(0, 100)
        for i in range(count):
            bg = create_premium_background(W, H, category=category, variant=i + variant_offset)
            composites.append(np.array(bg))
        return composites

    # === AUTO-TRIM white/light borders ===
    from engine.modules.image_utils import auto_trim_whitespace
    product_img = auto_trim_whitespace(product_img, is_transparent)

    pw, ph = product_img.size
    # Scale product to fill 85% of frame (centered, no white gaps)
    scale = min(W / pw, H / ph) * 0.75
    new_w, new_h = int(pw * scale), int(ph * scale)
    img_scaled = product_img.resize((new_w, new_h), Image.LANCZOS)

    vy_shifts = [0.0, -0.02, 0.02, -0.03, 0.03, -0.01, 0.01]
    variant_offset = random.randint(0, 100)
    for i in range(count):
        vy = vy_shifts[i % len(vy_shifts)]
        canvas = create_premium_background(W, H, category=category, variant=i + variant_offset)
        paste_x = (W - new_w) // 2
        paste_y = (H - new_h) // 2 + int(H * vy)
        paste_y = max(0, min(paste_y, H - new_h))
        add_product_shadow(canvas, img_scaled, paste_x, paste_y)
        if is_transparent:
            canvas.paste(img_scaled, (paste_x, paste_y), img_scaled.split()[3])
        else:
            canvas.paste(img_scaled, (paste_x, paste_y))
        composites.append(np.array(canvas))

    return composites


def _make_gradient_canvas(accent, index):
    """Last-resort gradient canvas (only if photo BG completely unavailable)."""
    grad = np.zeros((H, W, 3), dtype=np.uint8)
    hue_shift = index * 12
    top_color = tuple(min(255, max(0, c + hue_shift - 20)) for c in accent)
    bot_color = (15, 10, 20)
    for y in range(H):
        r = y / H
        for c in range(3):
            grad[y, :, c] = int(top_color[c] * (1 - r) + bot_color[c] * r)
    return Image.fromarray(grad)


def _ken_burns(composite_arr, t, duration, direction='zoom_in'):
    """Apply Ken Burns effect (zoom + pan) to a composite image."""
    h, w = composite_arr.shape[:2]
    progress = min(1.0, max(0.0, t / max(duration, 0.01)))

    directions = {
        'zoom_in':   (1.0, 1.15, 0.5, 0.5, 0.48, 0.45),
        'zoom_out':  (1.15, 1.0, 0.48, 0.45, 0.5, 0.5),
        'pan_left':  (1.10, 1.10, 0.55, 0.48, 0.45, 0.48),
        'pan_right': (1.10, 1.10, 0.45, 0.48, 0.55, 0.48),
        'pan_up':    (1.10, 1.10, 0.5, 0.55, 0.5, 0.42),
        'pan_down':  (1.10, 1.10, 0.5, 0.42, 0.5, 0.55),
    }
    ss, es, scx, scy, ecx, ecy = directions.get(direction, directions['zoom_in'])

    ease_p = 0.5 * (1 - math.cos(progress * math.pi))
    scale = ss + (es - ss) * ease_p
    cx = scx + (ecx - scx) * ease_p
    cy = scy + (ecy - scy) * ease_p

    crop_w = max(1, int(w / scale))
    crop_h = max(1, int(h / scale))
    x1 = max(0, min(int(cx * w - crop_w / 2), w - crop_w))
    y1 = max(0, min(int(cy * h - crop_h / 2), h - crop_h))

    cropped = composite_arr[y1:y1 + crop_h, x1:x1 + crop_w]
    return np.array(Image.fromarray(cropped).resize((W, H), Image.BILINEAR))


def _zoom_punch_transition(img1_arr, img2_arr, t, duration=0.5):
    """Zoom punch transition between two composite images."""
    progress = min(1.0, t / duration)
    if progress < 0.5:
        p = progress * 2
        frame = _ken_burns(img1_arr, p * 0.3, 1.0, 'zoom_in')
        fade = max(0, int((1.0 - p) * 255))
        return np.clip(frame * (fade / 255.0), 0, 255).astype(np.uint8)
    else:
        p = (progress - 0.5) * 2
        frame = _ken_burns(img2_arr, ease_out_cubic(p) * 0.2, 1.0, 'zoom_out')
        fade = min(255, int(p * 255))
        return np.clip(frame * (fade / 255.0), 0, 255).astype(np.uint8)


def _load_font(bold=False):
    """Load font, with fallback."""
    try:
        from font_helper import get_font, get_font_bold
        path = get_font_bold() if bold else get_font()
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    for candidate in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                      "arial.ttf"]:
        if os.path.exists(candidate):
            return candidate
    return None


def generate_long(queue_file, output_dir):
    """Generate YouTube Long-form using PRE-COMPOSITED images with Ken Burns animation."""
    print(f"Generating YouTube Long from {queue_file}...")

    if not os.path.exists(queue_file):
        print(f"Queue not found: {queue_file}")
        return

    init_sounds()
    os.makedirs(os.path.join(output_dir, "yt"), exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")

    jobs = []
    with open(queue_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                jobs.append(json.loads(line.strip()))

    long_jobs = [j for j in jobs if j.get('video_type', 'long') == 'long']
    if not long_jobs:
        long_jobs = jobs

    # NOTE: QC mode no longer limits videos — ALL accounts must render
    # Previously: limited to 2 videos in QC mode, causing missing v1_yt

    font_path = _load_font(bold=False)
    font_bold = _load_font(bold=True)
    dur_cfg = VIDEO_DURATION.get('yt_long', {'min': 90, 'max': 120})
    target_dur = random.randint(dur_cfg['min'], dur_cfg['max'])

    for job in long_jobs:
        produk_id = job['produk_id']
        acct_id = job.get('account_id', 'yt_1')
        acct_num = int(acct_id.split('_')[1]) if '_' in acct_id else 1
        category = get_category(acct_id)
        channel = get_channel_name(acct_id)
        accent = get_accent_color(category)

        print(f"\nRendering YT Long for {produk_id} ({acct_id}, {category})...")

        hooks = get_copywriting(category, 'hooks')
        ctas = get_copywriting(category, 'cta')
        hook_text = job.get('hook', random.choice(hooks) if hooks else 'Cek ini!')
        nama = job.get('nama', produk_id)
        from engine.modules.image_utils import clean_product_name
        nama = clean_product_name(nama)
        harga = job.get('harga', '')
        desc = job.get('deskripsi_singkat', '')
        cta_text = job.get('cta', random.choice(ctas) if ctas else 'Link di deskripsi!')
        rating_val = round(random.uniform(4.5, 4.9), 1)
        sold_count = random.randint(1000, 15000)

        # === DYNAMIC FLOW STAGES (YT Long 90-120s) ===
        # Stage 1: Nama + teaser slide in from LEFT
        # Stage 2: Nama exits LEFT, gambar product slides in from RIGHT
        # Stage 3: Gambar goyang kiri-kanan, nama+harga muncul di atas
        # Stage 4: Gambar exits RIGHT, fitur/review text slides in
        # Stage 5: Fitur exits, CTA penutup slides in
        
        S1_END = 10.0    # Nama + teaser
        S2_END = 14.0    # Transition: nama out, gambar in
        S3_END = 55.0    # Gambar goyang + info
        S4_END = 60.0    # Gambar out
        S5_END = 80.0    # Fitur/review text
        S6_END = 85.0    # Transition fitur out
        # S7 = 85 - total_dur: CTA
        
        SLIDE_DUR = 1.2  # Duration of slide animations
        PROD_SLIDE = 2.0  # Slower product entry

        try:
            # === LOAD COMPOSITE IMAGES (for backgrounds) ===
            composites = _load_composites(produk_id, category, count=7)
            print(f"  [OK] Loaded {len(composites)} composites")

            # Load product image separately for sway animation
            prod_img_pil = None
            for ext in ['png', 'jpg', 'webp']:
                p = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', f"{produk_id}.{ext}")
                if os.path.exists(p):
                    prod_img_pil = Image.open(p)
                    break
            
            # Scale product image for display
            if prod_img_pil:
                from engine.modules.image_utils import auto_trim_whitespace
                is_transp = prod_img_pil.mode == 'RGBA'
                if not is_transp:
                    prod_img_pil = prod_img_pil.convert('RGB')
                prod_img_pil = auto_trim_whitespace(prod_img_pil, is_transp)
                pw, ph = prod_img_pil.size
                prod_scale = min(W / pw, H / ph) * 0.90
                prod_w = int(pw * prod_scale)
                prod_h = int(ph * prod_scale)
                prod_img_pil = prod_img_pil.resize((prod_w, prod_h), Image.LANCZOS)
                if not is_transp:
                    prod_img_pil = prod_img_pil.convert('RGBA')
            
            # Frame border color (softer version of accent)
            border_color = tuple(min(255, c + 60) for c in accent)

            # Pre-render text overlays
            txt_w = W - 120
            
            # Stage 1: outline text (hollow, no bg) + teaser
            plain_bg = create_plain_gradient(accent, (W, H))
            nama_img = render_outline_text(nama, font_bold or font_path,
                                           80, outline_color=(255, 255, 255),
                                           stroke_width=3, max_width=txt_w)
            teaser_img = render_text_image(hook_text, font_path or "arial.ttf",
                                          42, (255, 255, 255), (0, 0, 0, 160), txt_w, 18,
                                          style='glass')
            
            # Stage 3: nama + harga (top bar - compact)
            top_nama_img = render_text_image(nama, font_bold or font_path,
                                            42, (255, 255, 255), (*accent, 220), txt_w, 16,
                                            style='clean')
            top_harga_img = None
            if harga:
                top_harga_img = create_simple_price(harga, font_bold or font_path or "arial.ttf",
                                                    46, accent)
            
            # Stage 5: fitur + review
            feat_text = f"{desc[:80]}" if desc else "Fitur unggulan produk ini"
            feat_img = render_text_image(feat_text, font_path or "arial.ttf",
                                         44, (255, 255, 255), (40, 167, 69, 220), txt_w, 20,
                                         style='glass')
            
            detail2_text = "Kualitas premium, tahan lama"
            detail2_img = render_text_image(detail2_text, font_path or "arial.ttf",
                                            42, (255, 255, 255), (0, 123, 255, 210), txt_w, 18,
                                            style='gradient_pill')
            
            review_text = "Bagus banget, sesuai deskripsi! Recommended "
            review_bubble = create_chat_bubble(review_text, font_path or "arial.ttf",
                                              side='left', accent_color=accent)
            
            verdict_text = f"Rating: {rating_val}/5 | {sold_count:,}+ Terjual"
            verdict_img = render_text_image(verdict_text, font_bold or font_path,
                                           44, (255, 255, 255), (40, 167, 69, 230), txt_w, 22,
                                           style='glow')
            
            # Stage 7: CTA
            cta_img = render_text_image(f" {cta_text}", font_bold or font_path,
                                        50, (255, 255, 255), (220, 53, 69, 240), txt_w, 24,
                                        style='gradient_pill')

            INTRO_SLIDE = 2.5  # Slow, gradual slide for Stage 1

            def make_frame(t):
                center_x = W // 2
                center_y = H // 2
                
                # ═══════════════════════════════════════════
                # STAGE 1: Plain bg + outline nama slides in slowly
                # ═══════════════════════════════════════════
                if t < S1_END:
                    # Use plain gradient background (NO product image)
                    frame = plain_bg.copy()
                    frame = draw_frame_border(frame, accent_color=border_color)
                    
                    # Nama outline slides in slowly from left (2.5s)
                    if t < INTRO_SLIDE:
                        x_off = slide_element_x(t, INTRO_SLIDE, 'in_left')
                    else:
                        x_off = 0
                    
                    nama_y = center_y - nama_img.height // 2 - 60
                    frame = paste_overlay_on_frame(frame, nama_img,
                        (center_x - nama_img.width // 2 + x_off, nama_y))
                    
                    # Teaser appears after 3s, also slow slide
                    if t > 3.0:
                        teaser_t = t - 3.0
                        tx_off = slide_element_x(teaser_t, 2.0, 'in_left') if teaser_t < 2.0 else 0
                        teaser_y = nama_y + nama_img.height + 35
                        frame = paste_overlay_on_frame(frame, teaser_img,
                            (center_x - teaser_img.width // 2 + tx_off, teaser_y))
                    
                    # Exit: slide out left (last 2s of stage)
                    exit_start = S1_END - 2.0
                    if t > exit_start:
                        exit_t = t - exit_start
                        x_out = slide_element_x(exit_t, 2.0, 'out_left')
                        frame2 = plain_bg.copy()
                        frame2 = draw_frame_border(frame2, accent_color=border_color)
                        frame2 = paste_overlay_on_frame(frame2, nama_img,
                            (center_x - nama_img.width // 2 + x_out, nama_y))
                        if t > 3.0:
                            frame2 = paste_overlay_on_frame(frame2, teaser_img,
                                (center_x - teaser_img.width // 2 + x_out, teaser_y))
                        frame = frame2
                
                # ═══════════════════════════════════════════
                # STAGE 2-3: Product image slides in + sways
                # ═══════════════════════════════════════════
                elif t < S4_END and prod_img_pil:
                    frame = plain_bg.copy()
                    frame = draw_frame_border(frame, accent_color=border_color)
                    prod_t = t - S1_END
                    
                    # Product slides in from right (first SLIDE_DUR)
                    if prod_t < PROD_SLIDE:
                        x_off = slide_element_x(prod_t, PROD_SLIDE, 'in_right')
                    # Product exits right (last 1.5s before S4_END)
                    elif t > S3_END:
                        exit_t = t - S3_END
                        x_off = slide_element_x(exit_t, S4_END - S3_END, 'out_right')
                    else:
                        # Sway left-right gently
                        x_off = sway_x(prod_t, amplitude=20, period=3.5)
                    
                    prod_x = center_x - prod_w // 2 + x_off
                    prod_y = center_y - prod_h // 2 + 40
                    frame = paste_overlay_on_frame(frame, prod_img_pil, (prod_x, prod_y))
                    
                    # Nama + harga appear at top after 3s into stage 2
                    if t > S2_END + 3.0 and t < S3_END:
                        info_t = t - (S2_END + 3.0)
                        info_opacity = min(1.0, info_t / 0.8)
                        
                        top_y = 80
                        frame = paste_overlay_on_frame(frame, top_nama_img,
                            (center_x - top_nama_img.width // 2, top_y), opacity=info_opacity)
                        if top_harga_img:
                            harga_y = top_y + top_nama_img.height + 8
                            frame = paste_overlay_on_frame(frame, top_harga_img,
                                (center_x - top_harga_img.width // 2, harga_y), opacity=info_opacity)
                
                # ═══════════════════════════════════════════
                # STAGE 5: Feature/review text
                # ═══════════════════════════════════════════
                elif t < S6_END:
                    frame = plain_bg.copy()
                    frame = draw_frame_border(frame, accent_color=border_color)
                    stage_t = t - S4_END
                    
                    # Nama exits left (first 1.2s)
                    if stage_t < SLIDE_DUR:
                        x_off = slide_element_x(stage_t, SLIDE_DUR, 'out_left')
                        frame = paste_overlay_on_frame(frame, top_nama_img,
                            (center_x - top_nama_img.width // 2 + x_off, 80))
                    
                    # Feature text slides in from right
                    feat_start = 1.0
                    if stage_t > feat_start:
                        ft = stage_t - feat_start
                        if ft < SLIDE_DUR:
                            fx_off = slide_element_x(ft, SLIDE_DUR, 'in_right')
                        else:
                            fx_off = 0
                        
                        feat_y = center_y - 200
                        frame = paste_overlay_on_frame(frame, feat_img,
                            (center_x - feat_img.width // 2 + fx_off, feat_y))
                    
                    # Detail2 slides in after 5s
                    if stage_t > 5.0:
                        d2t = stage_t - 5.0
                        if d2t < SLIDE_DUR:
                            d2_off = slide_element_x(d2t, SLIDE_DUR, 'in_left')
                        else:
                            d2_off = 0
                        d2_y = center_y - 20
                        frame = paste_overlay_on_frame(frame, detail2_img,
                            (center_x - detail2_img.width // 2 + d2_off, d2_y))
                    
                    # Review bubble after 8s
                    if stage_t > 8.0:
                        rb_t = stage_t - 8.0
                        if rb_t < SLIDE_DUR:
                            rb_off = slide_element_x(rb_t, SLIDE_DUR, 'in_left')
                        else:
                            rb_off = 0
                        frame = paste_overlay_on_frame(frame, review_bubble,
                            (80 + rb_off, center_y + 160))
                    
                    # Verdict after 12s
                    if stage_t > 12.0:
                        vt = stage_t - 12.0
                        if vt < SLIDE_DUR:
                            v_off = slide_element_x(vt, SLIDE_DUR, 'in_right')
                        else:
                            v_off = 0
                        frame = paste_overlay_on_frame(frame, verdict_img,
                            (center_x - verdict_img.width // 2 + v_off, center_y + 340))
                    
                    # Stars rating animation
                    if stage_t > 14.0:
                        stars = create_rating_stars(rating_val, font_path or "arial.ttf",
                                                   40, animated_t=stage_t - 14.0, total_dur=1.5)
                        frame = paste_overlay_on_frame(frame, stars,
                            (center_x - stars.width // 2, center_y + 500))
                    
                    # Exit all at end of stage
                    if t > S5_END:
                        exit_t = t - S5_END
                        x_out = slide_element_x(exit_t, S6_END - S5_END, 'out_right')
                        # Re-render with exit offset
                        frame2 = plain_bg.copy()
                        frame2 = draw_frame_border(frame2, accent_color=border_color)
                        # Move everything out to the right
                        if stage_t > feat_start:
                            frame2 = paste_overlay_on_frame(frame2, feat_img,
                                (center_x - feat_img.width // 2 + x_out, center_y - 200))
                        if stage_t > 5.0:
                            frame2 = paste_overlay_on_frame(frame2, detail2_img,
                                (center_x - detail2_img.width // 2 + x_out, center_y - 20))
                        if stage_t > 8.0:
                            frame2 = paste_overlay_on_frame(frame2, review_bubble,
                                (80 + x_out, center_y + 160))
                        if stage_t > 12.0:
                            frame2 = paste_overlay_on_frame(frame2, verdict_img,
                                (center_x - verdict_img.width // 2 + x_out, center_y + 340))
                        frame = frame2
                
                # ═══════════════════════════════════════════
                # STAGE 7: CTA closing
                # ═══════════════════════════════════════════
                else:
                    frame = plain_bg.copy()
                    frame = draw_frame_border(frame, accent_color=border_color)
                    cta_t = t - S6_END
                    
                    # CTA slides in from left
                    if cta_t < SLIDE_DUR:
                        cx_off = slide_element_x(cta_t, SLIDE_DUR, 'in_left')
                    else:
                        cx_off = 0
                    
                    cta_y = center_y - 100
                    frame = paste_overlay_on_frame(frame, cta_img,
                        (center_x - cta_img.width // 2 + cx_off, cta_y))
                    
                    # "STOK TERBATAS" blinks after 2s
                    if cta_t > 2.0:
                        blink = create_blinking_label(" STOK TERBATAS!",
                            font_bold or font_path or "arial.ttf",
                            (220, 53, 69), cta_t, 0.6)
                        frame = paste_overlay_on_frame(frame, blink,
                            (center_x - blink.width // 2, cta_y + cta_img.height + 30))
                    
                    # Rating stars after 4s
                    if cta_t > 4.0:
                        stars = create_rating_stars(rating_val, font_path or "arial.ttf", 40)
                        stars_y = cta_y + cta_img.height + 100
                        frame = paste_overlay_on_frame(frame, stars,
                            (center_x - stars.width // 2, stars_y))
                    
                    # Count-up "Terjual" after 5s
                    if cta_t > 5.0:
                        cnt_t = cta_t - 5.0
                        current = int(min(cnt_t / 3.0, 1.0) * sold_count)
                        cnt_img = create_count_up_text(current, "Terjual",
                            font_path or "arial.ttf", accent)
                        frame = paste_overlay_on_frame(frame, cnt_img,
                            (center_x - cnt_img.width // 2, cta_y + cta_img.height + 170))
                
                return frame

            # === ASSEMBLE VIDEO ===
            video = VideoClip(make_frame, duration=total_dur).with_fps(24)

            # === AUDIO (normalized) ===
            audio_clips = []
            # Get per-gender volume levels
            vo_vol, music_vol = get_voice_volumes(acct_id)

            music_dir = os.path.join(output_dir, "yt")
            music_path, music_tier = find_music_file(music_dir, produk_id, acct_id, category)
            if music_path:
                music = prepare_music(AudioFileClip(music_path), total_dur, music_vol=music_vol)
                audio_clips.append(music)

            # SFX at stage transitions
            stage_transitions = [S1_END, S2_END, S4_END, S6_END]
            for st_time in stage_transitions:
                sfx_path = get_sfx_path('swoosh')
                if sfx_path and os.path.exists(sfx_path) and st_time < total_dur:
                    try:
                        sfx = prepare_sfx(AudioFileClip(sfx_path), st_time)
                        audio_clips.append(sfx)
                    except Exception:
                        pass

            # Ding at rating stars (stage 5, 14s in)
            ding_time = S4_END + 14.0
            sfx_path = get_sfx_path('ding')
            if sfx_path and os.path.exists(sfx_path) and ding_time < total_dur:
                try:
                    sfx = prepare_sfx(AudioFileClip(sfx_path), ding_time)
                    audio_clips.append(sfx)
                except Exception:
                    pass

            # Bass drop at CTA
            cta_start = S6_END + 0.5
            sfx_path = get_sfx_path('bass_drop')
            if sfx_path and os.path.exists(sfx_path) and cta_start < total_dur:
                try:
                    sfx = prepare_sfx(AudioFileClip(sfx_path), cta_start)
                    audio_clips.append(sfx)
                except Exception:
                    pass

            if audio_clips:
                try:
                    video = video.with_audio(CompositeAudioClip(audio_clips))
                except Exception as e:
                    print(f"  [WARN] Audio failed: {e}")

            # === VOICEOVER: per-stage TTS ===
            vo_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers', produk_id, 'yt_long')
            vo_stages = [
                ('hook', 0.0), ('overview', S1_END), ('detail1', S2_END),
                ('detail2', S4_END), ('cta', S6_END)
            ]
            vo_found = False
            for idx, (stage_id, start_time) in enumerate(vo_stages):
                vo_path = os.path.join(vo_dir, f"vo_{stage_id}.mp3")
                if os.path.exists(vo_path) and start_time < total_dur:
                    try:
                        vo = AudioFileClip(vo_path)
                        if idx + 1 < len(vo_stages):
                            max_dur = vo_stages[idx + 1][1] - start_time - 0.3
                        else:
                            max_dur = total_dur - start_time - 0.2
                        if max_dur > 0.5 and vo.duration > max_dur:
                            vo = vo.subclipped(0, max_dur)
                        from engine.modules.audio_normalizer import normalize_audio_clip
                        vo = normalize_audio_clip(vo)
                        vo = vo.with_effects([afx.MultiplyVolume(vo_vol)])
                        vo = vo.with_start(start_time)
                        audio_clips.append(vo)
                        vo_found = True
                    except Exception:
                        pass
            if vo_found:
                try:
                    video = video.with_audio(CompositeAudioClip(audio_clips))
                except Exception:
                    pass

            # === EXPORT LONG ===
            out_file = f"{today}_{produk_id}_v{acct_num}_yt_long.mp4"
            out_path = os.path.join(output_dir, "yt", out_file)
            audio_params = get_ffmpeg_audio_params()
            video.write_videofile(out_path, fps=15, codec='libx264',
                                preset='ultrafast', logger=None,
                                **audio_params)
            print(f"  [OK] Long: {out_file} ({total_dur}s)")

            # === AUTO-EXTRACT SHORTS ===
            try:
                # Extract: Stage 1 (nama intro) + Stage 3 middle (product sway) + Stage 7 (CTA)
                hook_end = min(S1_END, total_dur)
                prod_mid_s = min(S2_END + 5, total_dur - 1)
                prod_mid_e = min(prod_mid_s + 15, S3_END, total_dur)
                cta_s = min(S6_END, total_dur - 1)
                cta_e = min(cta_s + 15, total_dur)

                if prod_mid_s >= total_dur or cta_s >= total_dur:
                    print(f"  [WARN] Shorts: video too short ({total_dur}s), skipping")
                else:
                    hook_clip = video.subclipped(0, hook_end)
                    prod_clip = video.subclipped(prod_mid_s, prod_mid_e)
                    cta_clip = video.subclipped(cta_s, cta_e)

                    shorts_video = concatenate_videoclips([hook_clip, prod_clip, cta_clip])
                    short_out = f"{today}_{produk_id}_v{acct_num}_yt.mp4"
                    short_path = os.path.join(output_dir, "yt", short_out)

                    if not os.path.exists(short_path):
                        shorts_video.write_videofile(short_path, fps=24, codec='libx264',
                                                   audio_codec='aac', preset='ultrafast',
                                                   logger=None)
                        print(f"  [OK] Short extracted: {short_out}")
                    shorts_video.close()
            except Exception as e:
                print(f"  [WARN] Shorts extraction failed: {e}")

            video.close()

        except Exception as e:
            import traceback
            print(f"  [FAIL] Long render: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    generate_long("engine/queue/yt_queue.jsonl", "engine/output")
