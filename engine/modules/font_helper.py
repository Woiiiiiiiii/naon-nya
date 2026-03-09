"""
font_helper.py
Cross-platform font resolver with Google Fonts auto-download.
Downloads Poppins (modern, versatile) for the video pipeline.
Falls back to DejaVu Sans on Linux, Arial on Windows.
"""
import os
import sys

FONT_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'fonts')

# Google Fonts URLs (direct TTF download)
GOOGLE_FONTS = {
    'poppins': {
        'regular': 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Medium.ttf',
        'bold': 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf',
        'light': 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Light.ttf',
        'semibold': 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-SemiBold.ttf',
    }
}


def _download_font(url, dest_path):
    """Download font file from URL."""
    try:
        import requests
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            with open(dest_path, 'wb') as f:
                f.write(resp.content)
            return True
    except Exception as e:
        print(f"  [WARN] Font download failed: {e}")
    return False


def _ensure_google_font(family='poppins', weight='regular'):
    """Ensure a Google Font is available locally, download if needed."""
    filename = f"{family}_{weight}.ttf"
    local_path = os.path.join(FONT_DIR, filename)

    if os.path.exists(local_path):
        return local_path

    url = GOOGLE_FONTS.get(family, {}).get(weight)
    if url and _download_font(url, local_path):
        print(f"  [OK] Downloaded font: {filename}")
        return local_path
    return None


def _find_system_font(bold=False):
    """Find a system font file as fallback."""
    candidates = []

    # Windows
    win_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
    if bold:
        candidates += [
            os.path.join(win_dir, 'arialbd.ttf'),
            os.path.join(win_dir, 'Arial Bold.ttf'),
        ]
    else:
        candidates += [
            os.path.join(win_dir, 'arial.ttf'),
            os.path.join(win_dir, 'Arial.ttf'),
        ]

    # Linux (DejaVu from fonts-dejavu-core package)
    linux_paths = [
        '/usr/share/fonts/truetype/dejavu',
        '/usr/share/fonts/dejavu',
        '/usr/share/fonts/TTF',
    ]
    for lp in linux_paths:
        if bold:
            candidates.append(os.path.join(lp, 'DejaVuSans-Bold.ttf'))
        else:
            candidates.append(os.path.join(lp, 'DejaVuSans.ttf'))

    # macOS
    if bold:
        candidates += ['/System/Library/Fonts/Helvetica-Bold.ttf']
    else:
        candidates += ['/System/Library/Fonts/Helvetica.ttf']

    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def get_font():
    """Get regular font path — prefers Poppins, falls back to system."""
    return _ensure_google_font('poppins', 'regular') or _find_system_font(False)


def get_font_bold():
    """Get bold font path — prefers Poppins Bold."""
    return _ensure_google_font('poppins', 'bold') or _find_system_font(True)


def get_font_light():
    """Get light font path — prefers Poppins Light."""
    return _ensure_google_font('poppins', 'light') or _find_system_font(False)


def get_font_semibold():
    """Get semibold font path — prefers Poppins SemiBold."""
    return _ensure_google_font('poppins', 'semibold') or _find_system_font(True)


# Pre-download all weights at import time (runs once during pipeline)
def init_fonts():
    """Download all font weights. Call once during pipeline setup."""
    for family in GOOGLE_FONTS:
        for weight in GOOGLE_FONTS[family]:
            _ensure_google_font(family, weight)


if __name__ == "__main__":
    init_fonts()
    print(f"Regular: {get_font()}")
    print(f"Bold:    {get_font_bold()}")
    print(f"Light:   {get_font_light()}")
    print(f"SemiBold:{get_font_semibold()}")
