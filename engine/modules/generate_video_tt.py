"""
generate_video_tt.py
TikTok: 25-30s FAST-PACED product review.

Architecture (per instruksi_upgrade_system.md Bagian 5):
  Uses PRE-COMPOSITED images animated with Ken Burns + fast transitions.
  Pace paling cepat, transisi agresif, teks besar dan bold.

Scenes:
  Hook(0-2s) -> Product(2-10s) -> Features(10-20s) -> CTA(20-30s)
"""
import json
import os
import sys
import random
import datetime
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from moviepy import (VideoClip, ImageClip, AudioFileClip,
                     CompositeAudioClip, afx, concatenate_audioclips)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from engine.modules.category_router import (
    get_category, get_accent_color, get_copywriting,
    get_channel_name, get_channel_motto, VIDEO_DURATION
)
from engine.modules.video_effects import (
    render_text_image, paste_overlay_on_frame,
    text_slide_up, ease_out_cubic, ease_out_back,
    create_rating_stars, create_blinking_label, create_count_up_text,
    create_simple_price,
    draw_frame_border, slide_element_x, sway_x,
    render_outline_text, create_plain_gradient
)
from engine.modules.sound_manager import get_sfx_path, init_sounds
from engine.modules.audio_normalizer import prepare_music, prepare_sfx, get_ffmpeg_audio_params, find_music_file, get_voice_volumes

W, H = 1080, 1920
COMPOSITES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'composites')

# TikTok neon theme
TT_ACCENT = (255, 0, 100)
TT_GRAD_TOP = (35, 0, 50)
TT_GRAD_BOT = (15, 0, 25)


def _load_composites(produk_id, category='home', count=4):
    """Generate FRESH composite images every run."""
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

    composites = _generate_fallback(produk_id, category, count)

    while len(composites) < count:
        composites.append(composites[len(composites) % max(1, len(composites))].copy())

    random.shuffle(composites)

    return composites


def _generate_fallback(produk_id, category, count=4):
    """Product image FILLS entire frame (cover mode) — sesuai acuan video.
    
    Layout stack:
      Layer 0: Blurred product image (full screen — bokeh effect)
      Layer 1: Sharp product image (cover — fills frame area)
      Layer 2: Frame border + text added later in make_frame()
    """
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
            bg = create_premium_background(W, H, category=category, variant=i + variant_offset, platform='tiktok')
            composites.append(np.array(bg))
        return composites

    # Auto-trim white borders from Shopee images
    from engine.modules.image_utils import auto_trim_whitespace
    product_img = auto_trim_whitespace(product_img, is_transparent)
    if product_img.mode == 'RGBA':
        product_img = product_img.convert('RGB')

    pw, ph = product_img.size

    # COVER MODE: fill entire canvas (may crop top/bottom or sides)
    cover_scale = max(W / pw, H / ph)
    cover_w, cover_h = int(pw * cover_scale), int(ph * cover_scale)
    img_cover = product_img.resize((cover_w, cover_h), Image.LANCZOS)
    cx = (cover_w - W) // 2
    cy = (cover_h - H) // 2
    img_cover = img_cover.crop((cx, cy, cx + W, cy + H))

    # Blurred version for edges outside pigura (bokeh effect sesuai acuan)
    img_blur = img_cover.filter(ImageFilter.GaussianBlur(radius=25))
    blur_arr = np.array(img_blur).astype(np.float32) * 0.7
    img_blur = Image.fromarray(np.clip(blur_arr, 0, 255).astype(np.uint8))

    # Sharp product fills inner frame area, blur fills outer edges
    # Aman karena Ken Burns sudah dihapus — boundary selalu sejajar pigura
    frame_margin = 22  # Match draw_frame_border margin

    for i in range(count):
        # Start with blurred bg (full canvas)
        canvas = img_blur.copy()
        # Paste sharp product inside pigura area
        inner_m = frame_margin + 4  # sedikit di dalam garis pigura
        inner_w = W - inner_m * 2
        inner_h = H - inner_m * 2
        # Cover mode for inner area
        inner_scale = max(inner_w / pw, inner_h / ph)
        fill_w = int(pw * inner_scale)
        fill_h = int(ph * inner_scale)
        img_fill = product_img.resize((fill_w, fill_h), Image.LANCZOS)
        fx = (fill_w - inner_w) // 2
        fy = (fill_h - inner_h) // 2
        img_fill = img_fill.crop((fx, fy, fx + inner_w, fy + inner_h))
        canvas.paste(img_fill, (inner_m, inner_m))
        composites.append(np.array(canvas))

    return composites


def _make_gradient(index):
    """Last-resort TikTok neon gradient."""
    grad = np.zeros((H, W, 3), dtype=np.uint8)
    top = tuple(min(255, c + index * 20) for c in TT_GRAD_TOP)
    for y in range(H):
        r = y / H
        for c in range(3):
            grad[y, :, c] = int(top[c] * (1 - r) + TT_GRAD_BOT[c] * r)
    return Image.fromarray(grad)


def _get_composite_frame(composites, t, cycle=8, dissolve_dur=0.5):
    """Static composite display with smooth cross-dissolve transitions.
    
    Product image stays FIXED in the frame (no zoom/pan that shifts alignment).
    Transitions between composites use smooth cross-dissolve.
    """
    idx = int(t / cycle) % len(composites)
    next_idx = (idx + 1) % len(composites)
    
    # Time within current cycle
    cycle_t = t % cycle
    
    # Cross-dissolve at end of each cycle
    if cycle_t > cycle - dissolve_dur:
        progress = (cycle_t - (cycle - dissolve_dur)) / dissolve_dur
        ease = progress * progress * (3 - 2 * progress)  # smoothstep
        blended = (composites[idx].astype(float) * (1 - ease) + 
                   composites[next_idx].astype(float) * ease)
        return np.clip(blended, 0, 255).astype(np.uint8)
    
    return composites[idx]


def _flash_cut(img1, img2, t, duration=0.25):
    """Fast flash cut transition — TikTok style."""
    progress = min(1.0, t / duration)
    if progress < 0.3:
        return img1
    elif progress < 0.5:
        # White flash
        return np.full_like(img1, 255)
    else:
        return img2


def _load_font(bold=False):
    try:
        from font_helper import get_font, get_font_bold
        path = get_font_bold() if bold else get_font()
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    for c in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf"]:
        if os.path.exists(c):
            return c
    return None


def generate_video_tt(queue_file, output_dir):
    """Generate TikTok videos using composite images with aggressive Ken Burns."""
    print(f"Generating TikTok videos from {queue_file}...")

    if not os.path.exists(queue_file):
        print(f"Queue not found: {queue_file}")
        return

    init_sounds()
    os.makedirs(os.path.join(output_dir, "tt"), exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")

    jobs = []
    with open(queue_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                jobs.append(json.loads(line.strip()))

    font_path = _load_font(bold=False)
    font_bold = _load_font(bold=True)
    dur_cfg = VIDEO_DURATION.get('tiktok', {'min': 25, 'max': 30})
    target_dur = random.randint(dur_cfg['min'], dur_cfg['max'])

    for job in jobs:
        produk_id = job['produk_id']
        acct_id = job.get('account_id', 'tt_1')
        category = get_category(acct_id)
        accent = get_accent_color(category)

        print(f"\nRendering TikTok for {produk_id} ({acct_id}, {category})...")

        hooks = get_copywriting(category, 'hooks')
        ctas = get_copywriting(category, 'cta')
        hook_text = job.get('hook', random.choice(hooks) if hooks else 'WAJIB PUNYA!')
        nama = job.get('nama', produk_id)
        from engine.modules.image_utils import clean_product_name
        nama = clean_product_name(nama)
        harga = job.get('harga', '')
        desc = job.get('deskripsi_singkat', '')
        cta_text = job.get('cta', random.choice(ctas) if ctas else 'Link di bio!')
        rating_val = round(random.uniform(4.5, 4.9), 1)
        sold_count = random.randint(500, 9999)

        total_dur = target_dur
        
        # === DYNAMIC FLOW STAGES (TT 25-30s — FAST PACE) ===
        S1_END = 4.0     # Nama + teaser (fast!)
        S2_END = 6.0     # Gambar masuk
        S3_END = 16.0    # Gambar goyang + info
        S4_END = 18.0    # Gambar keluar
        S5_END = 23.0    # Fitur text
        S6_END = 24.5    # Transition
        # S7 = 24.5 - total_dur: CTA
        
        SLIDE_DUR = 0.6  # FAST slides for TikTok
        PROD_SLIDE = 1.0  # Slower product entry

        try:
            composites = _load_composites(produk_id, category, count=4)
            print(f"  [OK] Loaded {len(composites)} composites")

            prod_img_pil = None
            for ext in ['png', 'jpg', 'webp']:
                p = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', f"{produk_id}.{ext}")
                if os.path.exists(p):
                    prod_img_pil = Image.open(p)
                    break
            
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
            
            border_color = tuple(min(255, c + 40) for c in TT_ACCENT)

            txt_w = W - 100
            
            plain_bg = create_plain_gradient(TT_ACCENT, (W, H))
            
            # Auto text color based on background brightness
            _lum = int(0.299 * TT_ACCENT[0] + 0.587 * TT_ACCENT[1] + 0.114 * TT_ACCENT[2])
            if _lum > 140:
                _nama_color = (30, 30, 40)
                _teaser_color = (60, 60, 70)
            else:
                _nama_color = (255, 255, 255)
                _teaser_color = (200, 200, 210)
            
            nama_img = render_outline_text(nama.title(), font_bold or font_path,
                                           90, outline_color=_nama_color,
                                           stroke_width=3, max_width=txt_w)
            teaser_img = render_outline_text(hook_text, font_path or "arial.ttf",
                                            42, outline_color=_teaser_color,
                                            stroke_width=2, max_width=txt_w)
            
            top_nama_img = render_outline_text(nama.title(), font_bold or font_path,
                                              44, outline_color=(255, 255, 255),
                                              stroke_width=3, max_width=txt_w)
            top_harga_img = None
            if harga:
                top_harga_img = render_outline_text(harga, font_bold or font_path or "arial.ttf",
                                                    50, outline_color=(255, 220, 100),
                                                    stroke_width=3, max_width=txt_w)
            
            feat_text = f"{desc[:60]}" if desc else "Fitur terbaik"
            feat_img = render_text_image(feat_text, font_path or "arial.ttf",
                                         44, (255, 255, 255), (*TT_ACCENT, 230), txt_w, 20,
                                         style='frosted')
            
            verdict_text = f"Rating {rating_val}/5 | {sold_count:,}+ Terjual"
            verdict_img = render_text_image(verdict_text, font_bold or font_path,
                                           42, (255, 255, 255), (*TT_ACCENT, 230), txt_w, 18,
                                           style='frosted')
            
            cta_img = render_text_image(f" {cta_text}", font_bold or font_path,
                                        54, (255, 255, 255), (220, 53, 69, 245), txt_w, 26,
                                        style='frosted')

            
            # Bottom bar: channel name + motto (persistent from Stage 2)
            _ch_name = get_channel_name('tt_1')
            _ch_motto = get_channel_motto('tt_1')
            bot_channel_img = render_outline_text(f"@{_ch_name}", font_bold or font_path,
                                                  38, outline_color=(255, 255, 255),
                                                  stroke_width=2, max_width=txt_w)
            bot_motto_img = None
            if _ch_motto:
                bot_motto_img = render_outline_text(_ch_motto, font_path or "arial.ttf",
                                                    28, outline_color=(220, 220, 230),
                                                    stroke_width=1, max_width=txt_w)

            INTRO_SLIDE = 1.2  # Faster for TikTok, but still gradual


            def make_frame(t):
                center_x = W // 2
                center_y = H // 2

                # Bottom bar helper (inside make_frame for center_x access)
                def _render_bottom_bar(frame):
                    bot_total_h = bot_channel_img.height + (bot_motto_img.height + 6 if bot_motto_img else 0)
                    bot_y = H - 90 - bot_total_h
                    frame = paste_overlay_on_frame(frame, bot_channel_img,
                        (center_x - bot_channel_img.width // 2, bot_y))
                    if bot_motto_img:
                        motto_y = bot_y + bot_channel_img.height + 6
                        frame = paste_overlay_on_frame(frame, bot_motto_img,
                            (center_x - bot_motto_img.width // 2, motto_y))
                    return frame
                
                if t < S1_END:
                    frame = plain_bg.copy()
                    frame = draw_frame_border(frame, accent_color=border_color, thickness=3, margin=22)
                    
                    nama_y = center_y - nama_img.height // 2 - 60
                    frame = paste_overlay_on_frame(frame, nama_img,
                        (center_x - nama_img.width // 2, nama_y))
                    
                    if t > 2.0:
                        _tt = t - 2.0
                        _t_opacity = min(1.0, _tt / 1.0)
                        teaser_y = nama_y + nama_img.height + 25
                        frame = paste_overlay_on_frame(frame, teaser_img,
                            (center_x - teaser_img.width // 2, teaser_y),
                            opacity=_t_opacity)
                    
                    if t > S1_END - 1.0:
                        exit_t = t - (S1_END - 1.0)
                        fade_out = max(0.0, 1.0 - exit_t / 1.0)
                        frame2 = plain_bg.copy()
                        frame2 = draw_frame_border(frame2, accent_color=border_color, thickness=3, margin=22)
                        frame2 = paste_overlay_on_frame(frame2, nama_img,
                            (center_x - nama_img.width // 2, nama_y), opacity=fade_out)
                        if t > 1.5:
                            frame2 = paste_overlay_on_frame(frame2, teaser_img,
                                (center_x - teaser_img.width // 2, teaser_y), opacity=fade_out)
                        frame = frame2
                
                elif t < S4_END:
                    frame = _get_composite_frame(composites, t, cycle=8)
                    frame = draw_frame_border(frame, accent_color=border_color, thickness=3, margin=22)
                    
                    # Persistent top bar + bottom bar (instant, no fade)
                    top_y = 25
                    frame = paste_overlay_on_frame(frame, top_nama_img,
                        (center_x - top_nama_img.width // 2, top_y))
                    if top_harga_img:
                        frame = paste_overlay_on_frame(frame, top_harga_img,
                            (center_x - top_harga_img.width // 2, top_y + top_nama_img.height + 8))
                    frame = _render_bottom_bar(frame)
                
                elif t < S6_END:
                    frame = _get_composite_frame(composites, t, cycle=8)
                    frame = draw_frame_border(frame, accent_color=border_color, thickness=3, margin=22)
                    stage_t = t - S4_END
                    
                    # Persistent nama + harga at top
                    info_total_h = top_nama_img.height + (top_harga_img.height + 8 if top_harga_img else 0)
                    top_y = 25
                    frame = paste_overlay_on_frame(frame, top_nama_img,
                        (center_x - top_nama_img.width // 2, top_y))
                    if top_harga_img:
                        harga_y = top_y + top_nama_img.height + 8
                        frame = paste_overlay_on_frame(frame, top_harga_img,
                            (center_x - top_harga_img.width // 2, harga_y))
                    
                    content_top = center_y - 200 + 25
                    frame = _render_bottom_bar(frame)
                    
                    if stage_t > 0.5:
                        ft = stage_t - 0.5
                        fx_off = slide_element_x(ft, SLIDE_DUR, 'in_right') if ft < SLIDE_DUR else 0
                        frame = paste_overlay_on_frame(frame, feat_img,
                            (center_x - feat_img.width // 2 + fx_off, content_top + 10))
                    
                    if stage_t > 2.5:
                        vt = stage_t - 2.5
                        v_off = slide_element_x(vt, SLIDE_DUR, 'in_left') if vt < SLIDE_DUR else 0
                        frame = paste_overlay_on_frame(frame, verdict_img,
                            (center_x - verdict_img.width // 2 + v_off, next_y + 10))
                    
                    if t > S5_END:
                        exit_t = t - S5_END
                        x_out = slide_element_x(exit_t, S6_END - S5_END, 'out_right')
                        frame2 = _get_composite_frame(composites, t, cycle=8)
                        frame2 = draw_frame_border(frame2, accent_color=border_color, thickness=3, margin=22)
                        frame2 = paste_overlay_on_frame(frame2, top_nama_img,
                            (center_x - top_nama_img.width // 2, top_y))
                        if top_harga_img:
                            frame2 = paste_overlay_on_frame(frame2, top_harga_img,
                                (center_x - top_harga_img.width // 2, harga_y))
                        if stage_t > 0.5:
                            frame2 = paste_overlay_on_frame(frame2, feat_img,
                                (center_x - feat_img.width // 2 + x_out, content_top + 10))
                        if stage_t > 2.5:
                            frame2 = paste_overlay_on_frame(frame2, verdict_img,
                                (center_x - verdict_img.width // 2 + x_out, next_y + 10))
                        frame2 = _render_bottom_bar(frame2)
                        frame = frame2
                
                else:
                    bg_idx = int(t / 8) % len(composites)
                    bg = composites[bg_idx]
                    frame = _get_composite_frame(composites, t, cycle=8)
                    frame = draw_frame_border(frame, accent_color=border_color, thickness=3, margin=22)

                    # Persistent top bar (nama + harga)
                    top_y = 25
                    frame = paste_overlay_on_frame(frame, top_nama_img,
                        (center_x - top_nama_img.width // 2, top_y))
                    if top_harga_img:
                        frame = paste_overlay_on_frame(frame, top_harga_img,
                            (center_x - top_harga_img.width // 2, top_y + top_nama_img.height + 8))
                    cta_t = t - S6_END
                    cx_off = slide_element_x(cta_t, SLIDE_DUR, 'in_left') if cta_t < SLIDE_DUR else 0
                    cta_y = center_y - 80
                    frame = paste_overlay_on_frame(frame, cta_img,
                        (center_x - cta_img.width // 2 + cx_off, cta_y))
                    frame = _render_bottom_bar(frame)
                
                return frame

            video = VideoClip(make_frame, duration=total_dur).with_fps(24)

            audio_clips = []
            vo_vol, music_vol = get_voice_volumes(acct_id)

            music_dir = os.path.join(output_dir, "tt")
            music_path, music_tier = find_music_file(music_dir, produk_id, acct_id, category)
            if music_path:
                music = prepare_music(AudioFileClip(music_path), total_dur, music_vol=music_vol)
                audio_clips.append(music)



            # Voiceover
            vo_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'voiceovers', produk_id, 'tt')
            vo_stages = [('hook', 0.0), ('product', S1_END), ('feature', S4_END), ('cta', S6_END)]
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
                    except Exception:
                        pass

            if audio_clips:
                try:
                    video = video.with_audio(CompositeAudioClip(audio_clips))
                except Exception as e:
                    print(f"  [WARN] Audio failed: {e}")

            out_file = f"{today}_{produk_id}_tt.mp4"
            out_path = os.path.join(output_dir, "tt", out_file)
            audio_params = get_ffmpeg_audio_params()
            video.write_videofile(out_path, fps=15, codec='libx264',
                                preset='ultrafast', logger=None,
                                **audio_params)
            print(f"  [OK] TikTok: {out_file} ({total_dur}s)")
            video.close()

        except Exception as e:
            import traceback
            print(f"  [FAIL] TikTok render: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    generate_video_tt("engine/queue/tt_queue.jsonl", "engine/output")
