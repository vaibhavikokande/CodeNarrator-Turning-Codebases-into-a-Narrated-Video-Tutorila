"""Download Roboto fonts from Google Fonts GitHub repo."""
import urllib.request
from pathlib import Path

FONTS_DIR = Path(__file__).parent

FONT_URLS = {
    "Roboto-Regular.ttf":     "https://github.com/google/fonts/raw/refs/heads/main/ofl/roboto/Roboto-Regular.ttf",
    "Roboto-Bold.ttf":        "https://github.com/google/fonts/raw/refs/heads/main/ofl/roboto/Roboto-Bold.ttf",
    "Roboto-Italic.ttf":      "https://github.com/google/fonts/raw/refs/heads/main/ofl/roboto/Roboto-Italic.ttf",
    "RobotoMono-Regular.ttf": "https://github.com/google/fonts/raw/refs/heads/main/ofl/robotomono/static/RobotoMono-Regular.ttf",
    # NotoSans covers Hindi, Chinese, Japanese, Korean, Arabic, and most other scripts.
    # Used as a Unicode fallback when Roboto cannot render a character.
    "NotoSans-Regular.ttf":   "https://github.com/google/fonts/raw/refs/heads/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf",
}

# System-level fallback paths for NotoSans-Regular (Linux / macOS / Windows)
_SYSTEM_UNICODE_FONTS = [
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
    "C:/Windows/Fonts/arialuni.ttf",
]


def ensure_fonts() -> None:
    missing = [name for name in FONT_URLS if not (FONTS_DIR / name).exists()]
    if not missing:
        return
    print(f"Downloading {len(missing)} font(s)...")
    for name in missing:
        dest = FONTS_DIR / name
        # For the Unicode fallback font, try system paths before downloading
        if name == "NotoSans-Regular.ttf":
            import shutil
            for sys_path in _SYSTEM_UNICODE_FONTS:
                if Path(sys_path).exists():
                    shutil.copy2(sys_path, dest)
                    print(f"  OK  {name} (copied from system)")
                    break
            if dest.exists():
                continue
        try:
            urllib.request.urlretrieve(FONT_URLS[name], dest)
            print(f"  OK  {name}")
        except Exception as exc:
            print(f"  FAIL  {name}: {exc}")


if __name__ == "__main__":
    ensure_fonts()
