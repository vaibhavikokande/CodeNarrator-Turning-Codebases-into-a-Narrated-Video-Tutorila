"""
generate_visuals.py â€” animated educational video clip renderer.

Each segment type is rendered as an animated MP4 clip (no audio) using
MoviePy VideoClip + Pillow frame-by-frame rendering with pre-cached base layers.

Segment types: title, chapter_intro, definition, code, architecture, summary, slide
"""

import asyncio
import io
import logging
import math
import random
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import base64
import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import TextLexer, guess_lexer
from pygments.styles import get_style_by_name

from pipeline.pocketflow import AsyncNode

logger = logging.getLogger(__name__)

# â”€â”€ Constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
W, H = 1920, 1080
FPS  = 8    # 8 fps â€” good enough for slide-style video, 33% faster than 12fps
FONTS_DIR = Path(__file__).parent.parent / "assets" / "fonts"

# Output resolution â€” render at full 1920Ã—1080 internally (so all layouts work),
# then downscale to 720p at encode time. Encoding 720p is ~2.5x faster than 1080p.
_OUT_W, _OUT_H = 1280, 720

# GitHub Dark palette
C_BG       = (13,  17,  23)
C_BG2      = (22,  27,  34)
C_BG3      = (33,  38,  45)
C_CARD     = (22,  27,  34)
C_TEXT     = (230, 237, 243)
C_MUTED    = (139, 148, 158)
C_ACCENT   = (88,  166, 255)   # #58a6ff
C_ACCENT2  = (31,  111, 235)   # #1f6feb
C_GREEN    = (63,  185, 80)
C_YELLOW   = (210, 153, 34)
C_PURPLE   = (188, 140, 255)
C_RED      = (248, 81,  73)
C_BORDER   = (48,  54,  61)

# â”€â”€ Font loading â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_FC: Dict[tuple, ImageFont.FreeTypeFont] = {}

def F(size: int, bold=False, italic=False, mono=False) -> ImageFont.FreeTypeFont:
    k = (size, bold, italic, mono)
    if k in _FC:
        return _FC[k]
    if mono:
        names = ["RobotoMono-Regular.ttf", "NotoSans-Regular.ttf"]
    elif bold:
        names = ["Roboto-Bold.ttf", "NotoSans-Regular.ttf"]
    elif italic:
        names = ["Roboto-Italic.ttf", "NotoSans-Regular.ttf"]
    else:
        names = ["Roboto-Regular.ttf", "NotoSans-Regular.ttf"]
    font = None
    for name in names:
        for d in [FONTS_DIR, Path(".")]:
            try:
                font = ImageFont.truetype(str(d / name), size)
                break
            except (IOError, OSError):
                pass
        if font:
            break
    if not font:
        font = ImageFont.load_default()
    _FC[k] = font
    return font

# â”€â”€ Animation math â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def ease_out(t: float) -> float:
    return 1 - (1 - max(0, min(1, t))) ** 3

def ease_in_out(t: float) -> float:
    t = max(0, min(1, t))
    return t * t * (3 - 2 * t)

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def progress(t: float, start: float, dur: float) -> float:
    return clamp01((t - start) / dur) if dur > 0 else (1.0 if t >= start else 0.0)

def alpha_int(p: float) -> int:
    return int(255 * p)

# â”€â”€ Pillow helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def grad_bg(colors: Tuple = (C_BG, C_BG2)) -> Image.Image:
    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    c1, c2 = colors
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)],
                  fill=(int(c1[0]+(c2[0]-c1[0])*t),
                        int(c1[1]+(c2[1]-c1[1])*t),
                        int(c1[2]+(c2[2]-c1[2])*t)))
    return img

def txt_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    try:
        return draw.textbbox((0, 0), text, font=font)[2]
    except AttributeError:
        return draw.textsize(text, font=font)[0]  # type: ignore

def txt_h(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    try:
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[3] - bb[1]
    except AttributeError:
        return draw.textsize(text, font=font)[1]  # type: ignore

def composite_rgba(base_rgb: Image.Image, layer_rgba: Image.Image,
                   pos: Tuple[int, int] = (0, 0)) -> Image.Image:
    base = base_rgb.convert("RGBA")
    over = Image.new("RGBA", base.size, (0, 0, 0, 0))
    over.paste(layer_rgba, pos)
    return Image.alpha_composite(base, over).convert("RGB")

def text_layer(text: str, font: ImageFont.FreeTypeFont, color: tuple,
               alpha: float, max_w: int = W) -> Image.Image:
    """Render text on transparent layer with given alpha."""
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tw = txt_w(dummy, text, font)
    th = txt_h(dummy, text, font)
    layer = Image.new("RGBA", (max(tw + 4, 1), max(th + 4, 1)), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(layer)
    draw.text((2, 2), text, font=font, fill=(*color, alpha_int(alpha)))
    return layer

def spotlight(img: Image.Image, cx: int, cy: int, radius: int,
              color=(88, 120, 200), intensity=40) -> Image.Image:
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)
    for r in range(radius, 0, -radius // 6):
        a = int(intensity * (1 - r / radius))
        draw.ellipse([(cx-r, cy-r), (cx+r, cy+r)], fill=(*color, a))
    return composite_rgba(img, overlay)

def rounded_rect_rgba(w: int, h: int, fill: tuple, radius=20,
                      border=None, border_w=2) -> Image.Image:
    img  = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, w-1, h-1], radius=radius,
                            fill=fill, outline=border, width=border_w)
    return img

def draw_watermark(img: Image.Image) -> None:
    draw = ImageDraw.Draw(img)
    txt  = "Generated by Code Narrator"
    font = F(20)
    w    = txt_w(draw, txt, font)
    draw.text((W - w - 24, H - 36), txt, font=font, fill=(*C_MUTED, 160))

def draw_visualizer(img: Image.Image, t: float, y_base: int = H - 30) -> None:
    """Fake animated audio visualizer bars at bottom."""
    draw = ImageDraw.Draw(img)
    n    = 80
    bw   = (W - 40) // n - 1
    for i in range(n):
        freq  = 0.4 + i * 0.06
        h_bar = int(22 * (0.25 + 0.75 * abs(math.sin(t * freq * 2.8 + i * 0.25))))
        x0    = 20 + i * (bw + 1)
        alpha = 120 + int(80 * abs(math.sin(t * 1.5 + i * 0.1)))
        draw.rectangle([x0, y_base - h_bar, x0 + bw, y_base],
                       fill=(*C_ACCENT, min(alpha, 200)))

# â”€â”€ Segment renderers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TitleRenderer:
    """TYPE 1 â€” Title slide with fade + subtle zoom + spotlight."""
    DUR = 3.0

    def __init__(self, data: dict):
        # display_content may be a plain string "Title\nTagline" or a dict
        raw_title = data.get("title", data.get("text", "Code Narrator"))
        if isinstance(raw_title, str) and "\n" in raw_title:
            parts          = raw_title.split("\n", 1)
            self.title     = parts[0].strip()
            self.subtitle  = data.get("subtitle", parts[1].strip())
        else:
            self.title    = str(raw_title).strip() or "Code Narrator"
            self.subtitle = data.get("subtitle", "")
        self.repo_url = data.get("repo_url", "")
        self._base    = self._prebuild()

    def _prebuild(self) -> Image.Image:
        img = grad_bg((C_BG, (26, 26, 46)))
        img = spotlight(img, W // 3, 0, 500, color=(88, 120, 200), intensity=30)
        img = spotlight(img, W * 2 // 3, 0, 400, color=(50, 80, 180), intensity=20)
        # Top accent bar
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0, 0), (W, 4)], fill=C_ACCENT2)
        draw_watermark(img)
        return img

    def make_frame(self, t: float) -> np.ndarray:
        frame = self._base.copy()

        # Title fade-in 0â†’1.5s
        p_title = ease_out(progress(t, 0, 1.5))
        if p_title > 0:
            tf    = F(82, bold=True)
            lines = textwrap.wrap(self.title, 30)
            y     = H // 2 - len(lines) * 95 - (40 if self.subtitle else 0)
            for line in lines:
                lay = text_layer(line, tf, C_TEXT, p_title)
                frame = composite_rgba(frame, lay,
                                       ((W - lay.width) // 2, y))
                y += 95
            # Underline
            if p_title > 0.5:
                draw = ImageDraw.Draw(frame)
                uw   = int(220 * p_title)
                draw.rectangle([(W//2 - uw//2, y+10), (W//2 + uw//2, y+14)],
                                fill=(*C_ACCENT, int(220 * p_title)))

        # Subtitle: slide up + fade in at 0.8s
        p_sub = ease_out(progress(t, 0.8, 0.7))
        if p_sub > 0 and self.subtitle:
            sf    = F(40, italic=True)
            y_off = int(20 * (1 - p_sub))
            lay   = text_layer(self.subtitle, sf, C_ACCENT, p_sub)
            y_sub = H // 2 + (len(textwrap.wrap(self.title, 30)) * 95) - (40 if self.subtitle else 0) + 30
            frame = composite_rgba(frame, lay,
                                   ((W - lay.width) // 2, y_sub - y_off))

        # Repo URL: fade in at 1.5s
        p_url = ease_in_out(progress(t, 1.5, 0.6))
        if p_url > 0 and self.repo_url:
            uf  = F(26, mono=True)
            lay = text_layer(self.repo_url[:70], uf, C_MUTED, p_url * 0.8)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, H // 2 + 200))

        # Visualizer
        draw_visualizer(frame, t)
        return np.array(frame)


class ChapterIntroRenderer:
    """TYPE 2 â€” Left panel slides in; right side has code rain."""
    DUR = 3.0

    def __init__(self, data: dict):
        self.num     = str(data.get("chapter_number", "01")).zfill(2)
        self.ctitle  = data.get("chapter_title", "")
        self.summary = data.get("summary", "")
        self._base   = grad_bg((C_BG, C_BG2))
        # Pre-render right panel with code rain base
        self._rain_chars = self._init_rain()

    def _init_rain(self):
        """Pre-compute code rain column data for determinism."""
        rng = random.Random(42)
        chars = "{}[]()<>|/;:.,!@#$%&*01ABCDEFGHIJKLabcdefghijklmnopqrstuvwxyz"
        cols  = []
        for x in range(W * 6 // 10 // 20):
            cols.append({
                "x":      W * 4 // 10 + x * 20,
                "speed":  rng.uniform(40, 100),
                "offset": rng.uniform(0, H),
                "chars":  [rng.choice(chars) for _ in range(H // 18 + 2)],
            })
        return cols

    def make_frame(self, t: float) -> np.ndarray:
        frame = self._base.copy().convert("RGBA")

        # â”€â”€ Right side: code rain â”€â”€
        rain_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        rd = ImageDraw.Draw(rain_layer)
        rf = F(15, mono=True)
        for col in self._rain_chars:
            for i, ch in enumerate(col["chars"]):
                y_pos = int((col["offset"] + i * 18 + t * col["speed"]) % (H + 36)) - 18
                if 0 <= y_pos < H:
                    brightness = max(0, 180 - i * 14)
                    alpha      = max(0, 120 - i * 10)
                    rd.text((col["x"], y_pos), ch, font=rf,
                            fill=(0, brightness, 80, alpha))
        # Blur the rain
        rain_blurred = rain_layer.filter(ImageFilter.GaussianBlur(radius=1))
        frame = Image.alpha_composite(frame, rain_blurred)

        # â”€â”€ Left panel: slides in from left â”€â”€
        p_panel = ease_out(progress(t, 0.0, 0.8))
        panel_x = int(-W * 4 // 10 * (1 - p_panel))
        panel_w = W * 4 // 10
        panel   = Image.new("RGBA", (panel_w, H), (22, 27, 34, 240))
        pd      = ImageDraw.Draw(panel)

        # Vertical accent line on right edge
        pd.rectangle([(panel_w - 4, 0), (panel_w, H)], fill=(*C_ACCENT2, 200))

        # Chapter number (count up)
        p_num   = ease_out(progress(t, 0.2, 0.6))
        cur_num = str(int(float(self.num) * p_num)).zfill(2)
        nf      = F(130, bold=True)
        pd.text((50, 80), cur_num, font=nf, fill=(*C_ACCENT, 80))

        # Chapter title
        p_ctitle = ease_out(progress(t, 0.6, 0.5))
        if p_ctitle > 0:
            tf = F(44, bold=True)
            pd.text((50, 260), self.ctitle[:32], font=tf,
                    fill=(*C_TEXT, alpha_int(p_ctitle)))

        # Summary
        p_sum = ease_out(progress(t, 1.0, 0.5))
        if p_sum > 0:
            sf = F(26)
            y  = 330
            for line in textwrap.wrap(self.summary, 34)[:4]:
                pd.text((50, y), line, font=sf, fill=(*C_MUTED, alpha_int(p_sum)))
                y += 38

        frame = composite_rgba(frame.convert("RGB"), panel, (panel_x, 0))
        draw_visualizer(frame, t)
        return np.array(frame)


class DefinitionRenderer:
    """TYPE 3 â€” Top bar slides down; card fades in; bullets appear one-by-one."""
    DUR = 3.0

    def __init__(self, data: dict):
        self.concept = data.get("concept", data.get("term", "Concept"))
        self.defn    = data.get("definition", data.get("text", ""))
        self.points  = data.get("key_points", [])[:5]
        self.analogy = data.get("analogy", "")
        self._base   = grad_bg((C_BG, C_BG2))

    def make_frame(self, t: float) -> np.ndarray:
        frame = self._base.copy()
        draw  = ImageDraw.Draw(frame)

        # â”€â”€ Top bar slides down 0â€“0.4s â”€â”€
        p_bar = ease_out(progress(t, 0.0, 0.4))
        bar_h = 88
        bar_y = int(-bar_h + bar_h * p_bar)
        draw.rectangle([(0, bar_y), (W, bar_y + bar_h)], fill=C_ACCENT2)
        if p_bar > 0.2:
            tf = F(34, bold=True)
            draw.text((40, bar_y + (bar_h - 34) // 2), self.concept[:60],
                      font=tf, fill=C_TEXT)

        # â”€â”€ Card fades in 0.5â€“1.0s â”€â”€
        p_card = ease_in_out(progress(t, 0.5, 0.5))
        if p_card > 0:
            card_w, card_h = W - 160, 480
            card_x, card_y = 80, bar_h + 60
            crect = rounded_rect_rgba(card_w, card_h, (*C_CARD, alpha_int(p_card)),
                                      radius=16, border=(*C_BORDER, alpha_int(p_card)))
            frame = composite_rgba(frame, crect, (card_x, card_y))
            draw  = ImageDraw.Draw(frame)

            # DEFINITION label
            lf = F(20, bold=True)
            draw.text((card_x + 36, card_y + 30), "DEFINITION",
                      font=lf, fill=(*C_ACCENT, alpha_int(p_card)))
            # Underline label
            draw.rectangle([(card_x + 36, card_y + 56),
                             (card_x + 160, card_y + 59)],
                            fill=(*C_ACCENT, alpha_int(p_card)))

            # Definition text
            df = F(34)
            y  = card_y + 74
            for line in textwrap.wrap(self.defn, 62)[:3]:
                draw.text((card_x + 36, y), line, font=df,
                          fill=(*C_TEXT, alpha_int(p_card)))
                y += 46

            # Divider
            div_y = card_y + 220
            draw.rectangle([(card_x + 36, div_y), (card_x + card_w - 36, div_y + 1)],
                            fill=(*C_BORDER, alpha_int(p_card)))

            # KEY POINTS label
            draw.text((card_x + 36, div_y + 14), "KEY POINTS",
                      font=lf, fill=(*C_GREEN, alpha_int(p_card)))

        # â”€â”€ Bullet points: one every 1.2s starting at t=1.5 â”€â”€
        bp_font = F(32)
        for i, point in enumerate(self.points):
            p_bullet = ease_out(progress(t, 1.5 + i * 1.2, 0.4))
            if p_bullet > 0:
                bx = 116
                by = 388 + i * 52 + bar_h - 50
                # Bullet circle
                draw = ImageDraw.Draw(frame)
                cr = 9
                draw.ellipse([(bx - cr, by + 6), (bx + cr, by + 6 + cr*2)],
                              fill=(*C_ACCENT, alpha_int(p_bullet)))
                lay = text_layer(point[:70], bp_font, C_TEXT, p_bullet)
                frame = composite_rgba(frame, lay, (bx + 20, by))
                draw  = ImageDraw.Draw(frame)

        # â”€â”€ Analogy box slides up from bottom at t=7.0 â”€â”€
        p_analogy = ease_out(progress(t, 4.5, 0.6))
        if p_analogy > 0 and self.analogy:
            box_h  = 100
            box_y  = H - box_h - 30 - int(20 * (1 - p_analogy))
            draw.rectangle([(80, box_y), (W - 80, box_y + box_h)],
                           fill=(*C_BG3, alpha_int(p_analogy * 0.9)))
            draw.rectangle([(80, box_y), (86, box_y + box_h)],
                           fill=(*C_YELLOW, alpha_int(p_analogy)))
            draw.text((100, box_y + 12), "Real-world analogy",
                      font=F(22, bold=True), fill=(*C_YELLOW, alpha_int(p_analogy)))
            for line in textwrap.wrap(self.analogy, 90)[:2]:
                draw.text((100, box_y + 42), line,
                          font=F(26, italic=True), fill=(*C_MUTED, alpha_int(p_analogy)))

        draw_visualizer(frame, t)
        return np.array(frame)


class CodeRenderer:
    """TYPE 4 â€” Glassmorphism IDE card: code types in left panel with syntax
    colour hints; explanation bullets cascade in the right panel."""
    DUR = 3.0

    # Simple keyword â†’ colour map for a few common languages
    _KW_COLORS = {
        "def": C_PURPLE, "class": C_PURPLE, "return": C_RED, "import": C_ACCENT,
        "from": C_ACCENT, "if": C_RED, "else": C_RED, "elif": C_RED,
        "for": C_YELLOW, "while": C_YELLOW, "in": C_YELLOW, "not": C_RED,
        "and": C_RED, "or": C_RED, "True": C_GREEN, "False": C_GREEN,
        "None": C_GREEN, "async": C_PURPLE, "await": C_PURPLE,
        "function": C_PURPLE, "const": C_ACCENT, "let": C_ACCENT,
        "var": C_ACCENT, "=>": C_YELLOW,
    }

    def __init__(self, data: dict):
        raw_code          = data.get("code", data.get("text", "# No code"))
        self.code_lines   = raw_code.splitlines()
        self.language     = data.get("language", "python")
        self.highlight_ln = data.get("highlight_line", -1)
        self.points       = data.get("explanation_points", [])[:4]
        self.filename     = data.get("filename", "")
        self.purpose      = data.get("purpose", "")

    def _prebuild_bg(self) -> Image.Image:
        img = grad_bg(((4, 6, 14), (14, 18, 30)))
        # Subtle grid overlay
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for x in range(0, W, 64):
            od.line([(x, 0), (x, H)], fill=(*C_ACCENT, 6))
        for y in range(0, H, 64):
            od.line([(0, y), (W, y)], fill=(*C_ACCENT, 6))
        return composite_rgba(img, overlay)

    @staticmethod
    def _colorize(line: str) -> List[Tuple[str, tuple]]:
        """Return list of (token_str, rgb_color) for a code line."""
        tokens = []
        i = 0
        words = re.split(r"(\s+|[(){}[\],.:\"'#])", line)
        for w in words:
            color = CodeRenderer._KW_COLORS.get(w, None)
            if color:
                tokens.append((w, color))
            elif w.startswith("#") or w.startswith("//"):
                tokens.append((w, (101, 109, 118)))
            elif w.startswith('"') or w.startswith("'"):
                tokens.append((w, (152, 195, 121)))
            elif w.isdigit():
                tokens.append((w, (209, 154, 102)))
            else:
                tokens.append((w, C_TEXT))
        return tokens

    def make_frame(self, t: float) -> np.ndarray:
        frame = self._prebuild_bg()

        # â”€â”€ Code panel (glassmorphism card, left 55 %) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        p_card = ease_out(progress(t, 0.0, 0.4))
        card_w = int(W * 0.55)
        card_h = H - 80
        card_x, card_y = 36, 40
        if p_card > 0:
            card_bg = rounded_rect_rgba(card_w, card_h,
                                        (14, 20, 32, alpha_int(p_card * 0.92)),
                                        radius=18,
                                        border=(*C_BORDER, alpha_int(p_card * 0.8)))
            frame = composite_rgba(frame, card_bg, (card_x, card_y))

        draw = ImageDraw.Draw(frame)

        # Header bar inside card
        p_hdr = ease_out(progress(t, 0.1, 0.35))
        if p_hdr > 0:
            hbar = rounded_rect_rgba(card_w, 44, (*C_BG2, alpha_int(p_hdr)),
                                     radius=18)
            # Only round top corners â€” overdraw bottom half
            frame = composite_rgba(frame, hbar, (card_x, card_y))
            draw  = ImageDraw.Draw(frame)
            # Traffic-light dots
            for xi, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
                dx = card_x + 20 + xi * 22
                draw.ellipse([(dx, card_y + 14), (dx + 14, card_y + 28)], fill=col)
            # File name
            if self.filename:
                draw.text((card_x + 90, card_y + 12), self.filename,
                          font=F(20, mono=True), fill=C_MUTED)

        # Code lines typing in
        cf         = F(21, mono=True)
        lh         = 30
        y_start    = card_y + 54
        max_vis    = (H - 160) // lh
        visible_ln = min(int(t / 0.14) + 1, len(self.code_lines))

        for i, line in enumerate(self.code_lines[:max_vis]):
            if i >= visible_ln:
                break
            y = y_start + i * lh

            # Highlight row
            if i + 1 == self.highlight_ln:
                pulse = 0.55 + 0.45 * math.sin(t * 3.5)
                hl    = rounded_rect_rgba(card_w - 12, lh + 2,
                                          (60, 50, 0, int(120 * pulse)), radius=4)
                frame = composite_rgba(frame, hl, (card_x + 6, y - 2))
                draw  = ImageDraw.Draw(frame)

            # Line number
            draw.text((card_x + 12, y), f"{i+1:3}", font=cf, fill=(*C_MUTED, 160))

            # Coloured tokens
            tokens = CodeRenderer._colorize(line[:65])
            tx = card_x + 56
            for tok, col in tokens:
                draw.text((tx, y), tok, font=cf, fill=col)
                try:
                    tw = draw.textbbox((0, 0), tok, font=cf)[2]
                except Exception:
                    tw = len(tok) * 12
                tx += tw

        # Active cursor blink on last visible line
        if visible_ln < len(self.code_lines):
            cy_cur = y_start + visible_ln * lh
            if int(t * 2) % 2 == 0:
                draw.rectangle([(card_x + 56, cy_cur),
                                 (card_x + 58 + 10, cy_cur + lh - 4)],
                                fill=(*C_ACCENT, 200))

        # â”€â”€ Right panel: explanation (glassmorphism) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        code_done_t = len(self.code_lines) * 0.14 + 0.6
        p_right = ease_out(progress(t, code_done_t, 0.7))
        if p_right > 0:
            rx, ry   = W * 55 // 100 + 30, 40
            rw, rh   = W - rx - 30, H - 80
            right_bg = rounded_rect_rgba(rw, rh,
                                          (16, 22, 36, alpha_int(p_right * 0.88)),
                                          radius=18,
                                          border=(*C_BORDER, alpha_int(p_right * 0.7)))
            frame = composite_rgba(frame, right_bg, (rx, ry))
            draw  = ImageDraw.Draw(frame)

            # Language badge
            draw.rounded_rectangle([(rx + 16, ry + 16), (rx + 120, ry + 42)],
                                   radius=8, fill=(*C_ACCENT2, alpha_int(p_right * 0.5)))
            draw.text((rx + 24, ry + 20), self.language.upper()[:10],
                      font=F(18, bold=True), fill=(*C_ACCENT, alpha_int(p_right)))

            # Purpose
            if self.purpose:
                py_off = int(14 * (1 - p_right))
                pf     = F(22, bold=True)
                draw.text((rx + 18, ry + 58 - py_off), f"// {self.purpose[:36]}",
                          font=pf, fill=(*C_GREEN, alpha_int(p_right * 0.9)))

            # Explanation bullets with stagger
            for bi, point in enumerate(self.points):
                bp = ease_out(progress(t, code_done_t + 0.4 + bi * 0.45, 0.35))
                if bp > 0:
                    by = ry + 106 + bi * 68
                    # Numbered circle
                    nc  = rounded_rect_rgba(30, 30, (*C_ACCENT2, alpha_int(bp * 0.4)), radius=15)
                    frame = composite_rgba(frame, nc, (rx + 16, by))
                    draw  = ImageDraw.Draw(frame)
                    draw.text((rx + 23, by + 4), str(bi + 1),
                              font=F(17, bold=True), fill=(*C_ACCENT, alpha_int(bp)))
                    # Bullet text
                    ef = F(27)
                    for li, wl in enumerate(textwrap.wrap(point[:80], 32)[:2]):
                        lay = text_layer(wl, ef, C_TEXT, bp)
                        frame = composite_rgba(frame, lay, (rx + 54, by + li * 34))

        draw_visualizer(frame, t)
        return np.array(frame)


class ArchitectureRenderer:
    """TYPE 5 â€” Diagram fades in with zoom; manual fallback draws boxes."""
    DUR = 4.5

    def __init__(self, data: dict, diagram_img: Optional[Image.Image]):
        self.mermaid_src = data.get("mermaid_source", data.get("text", ""))
        self.summary     = data.get("summary", "")
        self.diagram     = diagram_img
        self._base       = grad_bg((C_BG, (20, 20, 40)))

    def make_frame(self, t: float) -> np.ndarray:
        frame = self._base.copy()
        draw  = ImageDraw.Draw(frame)

        # Title
        p_title = ease_out(progress(t, 0, 0.5))
        if p_title > 0:
            tf  = F(52, bold=True)
            ttl = "Architecture Overview"
            tw  = txt_w(draw, ttl, tf)
            lay = text_layer(ttl, tf, C_TEXT, p_title)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, 40))
            draw  = ImageDraw.Draw(frame)

        # Diagram: zoom 0.95â†’1.0 and fade in starting at t=0.5
        p_diag = ease_in_out(progress(t, 0.5, 0.8))
        if p_diag > 0 and self.diagram:
            zoom_scale = 0.95 + 0.05 * p_diag
            dw = int(self.diagram.width * zoom_scale)
            dh = int(self.diagram.height * zoom_scale)
            # Fit diagram
            max_dw = W - 100
            max_dh = H - 200
            if dw > max_dw:
                scale = max_dw / dw
                dw, dh = int(dw * scale), int(dh * scale)
            if dh > max_dh:
                scale = max_dh / dh
                dw, dh = int(dw * scale), int(dh * scale)
            resized = self.diagram.resize((dw, dh), Image.LANCZOS)
            diag_layer = Image.new("RGBA", (dw, dh), (0, 0, 0, 0))
            diag_rgb   = resized.convert("RGBA")
            diag_rgb.putalpha(alpha_int(p_diag))
            frame = composite_rgba(frame, diag_rgb,
                                   ((W - dw) // 2, 130 + (H - 200 - dh) // 2))
        elif p_diag > 0:
            # Fallback: draw the mermaid source as a text slide
            draw = ImageDraw.Draw(frame)
            sf   = F(22, mono=True)
            y    = 150
            for line in self.mermaid_src.splitlines()[:20]:
                lay = text_layer(line[:80], sf, C_MUTED, p_diag)
                frame = composite_rgba(frame, lay, (100, y))
                y += 28

        # Summary
        p_sum = ease_out(progress(t, 2.0, 0.5))
        if p_sum > 0 and self.summary:
            draw = ImageDraw.Draw(frame)
            for i, line in enumerate(textwrap.wrap(self.summary, 80)[:2]):
                lay = text_layer(line, F(28), C_MUTED, p_sum * 0.8)
                frame = composite_rgba(frame, lay, ((W - lay.width) // 2, H - 100 + i * 36))

        draw_visualizer(frame, t)
        return np.array(frame)


class SummaryRenderer:
    """TYPE 6 â€” Takeaways slide in from right; branding fades in last."""
    DUR = 4.5

    def __init__(self, data: dict):
        self.heading    = data.get("heading", "Summary")
        self.takeaways  = data.get("takeaways", [])[:6]
        self.next_ch    = data.get("next_chapter", "")
        self._base      = self._prebuild()

    def _prebuild(self) -> Image.Image:
        img = grad_bg((C_BG, (26, 26, 46)))
        img = spotlight(img, W // 2, 0, 600, color=(50, 80, 180), intensity=20)
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0, 0), (W, 4)], fill=C_ACCENT2)
        draw_watermark(img)
        return img

    def make_frame(self, t: float) -> np.ndarray:
        frame = self._base.copy()

        # Heading
        p_h = ease_out(progress(t, 0, 0.6))
        if p_h > 0:
            hf  = F(64, bold=True)
            lay = text_layer(self.heading, hf, C_TEXT, p_h)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, 120))

        # Takeaways: slide in from right
        tf = F(36)
        for i, item in enumerate(self.takeaways):
            p_item = ease_out(progress(t, 0.8 + i * 0.5, 0.4))
            if p_item > 0:
                x_off = int(120 * (1 - p_item))
                # Number badge
                num_layer = text_layer(f"{i+1}", F(32, bold=True), C_ACCENT, p_item)
                frame = composite_rgba(frame, num_layer, (160 + x_off, 260 + i * 72))
                # Text
                txt_l = text_layer(textwrap.shorten(item, 68, placeholder='â€¦'), tf, C_TEXT, p_item)
                frame = composite_rgba(frame, txt_l, (210 + x_off, 262 + i * 72))

        # Next chapter hint
        p_next = ease_out(progress(t, len(self.takeaways) * 0.5 + 1.0, 0.5))
        if p_next > 0 and self.next_ch:
            nl  = text_layer(f"Next â†’ {self.next_ch}", F(32, italic=True), C_ACCENT, p_next)
            frame = composite_rgba(frame, nl, ((W - nl.width) // 2, H - 120))

        draw_visualizer(frame, t)
        return np.array(frame)


class SlideRenderer:
    """Generic slide: glassmorphism card + title + body with Ken Burns zoom."""
    DUR = 3.0

    # Accent colours cycle per slide instance (via hash of title)
    _ACCENTS = [C_ACCENT, C_GREEN, C_PURPLE, C_YELLOW]

    def __init__(self, data: dict):
        if isinstance(data, str):
            lines      = data.strip().splitlines()
            self.title = lines[0] if lines else ""
            self.body  = "\n".join(lines[1:]) if len(lines) > 1 else ""
        else:
            self.title = data.get("title", data.get("text", ""))
            self.body  = data.get("body", data.get("subtitle", ""))
        self.accent = self._ACCENTS[abs(hash(self.title)) % len(self._ACCENTS)]
        self._base  = self._prebuild()

    def _prebuild(self) -> Image.Image:
        # Rich gradient: dark teal â†’ deep purple
        img  = grad_bg(((6, 8, 18), (20, 14, 42)))
        img  = spotlight(img, W * 2 // 3, H // 3, 500,
                         color=self.accent, intensity=18)
        # Decorative corner geometry
        draw = ImageDraw.Draw(img)
        for i in range(4):
            r  = 80 + i * 55
            a  = int(10 - i * 2)
            draw.arc([(W - r - 40, -r + 40), (W - 40 + r, 40 + r)],
                     start=200, end=300, fill=(*self.accent, a), width=2)
        draw.rectangle([(0, 0), (W, 5)], fill=self.accent)
        return img

    def make_frame(self, t: float) -> np.ndarray:
        # Ken Burns: slow zoom 1.0 â†’ 1.03 over the full clip
        zoom = 1.0 + 0.03 * ease_in_out(t / self.DUR)
        # Pan: gentle leftward drift
        dx   = int(W * (zoom - 1.0) * -0.4)
        dy   = int(H * (zoom - 1.0) * -0.25)
        frame_big = self._base.resize((int(W * zoom), int(H * zoom)), Image.LANCZOS)
        frame = frame_big.crop((dx if dx < 0 else 0, 0,
                                 (dx if dx < 0 else 0) + W, H)).convert("RGB")
        frame = frame.resize((W, H), Image.LANCZOS)

        # Central glassmorphism card slides up + fades
        p_card = ease_out(progress(t, 0.0, 0.5))
        if p_card > 0:
            cw, ch   = W - 280, H - 280
            cx, cy_b = 140, 120
            cy_off   = int(30 * (1 - p_card))
            card_bg  = rounded_rect_rgba(cw, ch,
                                          (*C_BG, alpha_int(p_card * 0.82)),
                                          radius=24,
                                          border=(*self.accent, alpha_int(p_card * 0.45)))
            frame = composite_rgba(frame, card_bg, (cx, cy_b + cy_off))

        draw = ImageDraw.Draw(frame)

        # Accent left stripe on card
        p_stripe = ease_out(progress(t, 0.15, 0.4))
        if p_stripe > 0:
            sh = int((H - 280) * p_stripe)
            draw.rounded_rectangle([(140, 120), (148, 120 + sh)],
                                   radius=4, fill=(*self.accent, alpha_int(p_stripe)))

        # Title with subtle bounce
        p_title = ease_out(progress(t, 0.2, 0.55))
        if p_title > 0:
            y_off = int(16 * (1 - p_title))
            tf    = F(68, bold=True)
            lay   = text_layer(textwrap.shorten(self.title, 48, placeholder='â€¦'), tf, C_TEXT, p_title)
            frame = composite_rgba(frame, lay, (200, 150 + y_off))
            draw  = ImageDraw.Draw(frame)
            # Underline sweeps in
            uw = int(lay.width * ease_out(progress(t, 0.55, 0.35)))
            if uw > 0:
                draw.rectangle([(200, 150 + lay.height + 6),
                                 (200 + uw, 150 + lay.height + 10)],
                                fill=(*self.accent, 210))

        # Body text with staggered word-wrap lines
        p_body = ease_out(progress(t, 0.65, 0.5))
        if p_body > 0 and self.body:
            bf   = F(36)
            body_lines = textwrap.wrap(self.body, 62)[:7]
            for li, line in enumerate(body_lines):
                lp  = ease_out(progress(t, 0.65 + li * 0.12, 0.4))
                if lp > 0:
                    lay = text_layer(line, bf, C_MUTED, lp)
                    frame = composite_rgba(frame, lay, (200, 270 + li * 52))

        draw_visualizer(frame, t)
        return np.array(frame)


class BulletsRenderer:
    """Bullets slide â€” two-column card layout with icon badges and stagger."""
    DUR = 4.5

    _BULLET_ICONS = ["â—", "â—†", "â–²", "â˜…", "â– ", "â—‰"]
    _BULLET_COLS  = [C_ACCENT, C_GREEN, C_PURPLE, C_YELLOW, C_RED, C_ACCENT2]

    def __init__(self, data: dict):
        if isinstance(data, str):
            lines       = data.strip().splitlines()
            self.title  = lines[0] if lines else ""
            self.points = [l.lstrip("-â€¢\xb7 ") for l in lines[1:] if l.strip()][:6]
        else:
            self.title  = data.get("title", data.get("text", ""))
            self.points = data.get("key_points", data.get("points", []))[:6]
        self._base = self._prebuild()

    def _prebuild(self) -> Image.Image:
        img = grad_bg(((6, 8, 18), (18, 14, 38)))
        img = spotlight(img, W // 4, 0, 500, color=(50, 80, 200), intensity=20)
        img = spotlight(img, W * 3 // 4, H, 400, color=(80, 50, 160), intensity=15)
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0, 0), (W, 5)], fill=C_ACCENT2)
        return img

    def make_frame(self, t: float) -> np.ndarray:
        frame = self._base.copy()
        draw  = ImageDraw.Draw(frame)

        # Title bar sweeps in from left
        p_bar = ease_out(progress(t, 0.0, 0.45))
        if p_bar > 0:
            bw     = int(W * p_bar)
            bar_bg = Image.new("RGBA", (bw, 108), (0, 0, 0, 0))
            bd     = ImageDraw.Draw(bar_bg)
            bd.rectangle([(0, 0), (bw, 108)], fill=(*C_ACCENT2, 60))
            frame = composite_rgba(frame, bar_bg, (0, 0))
            draw  = ImageDraw.Draw(frame)

        p_title = ease_out(progress(t, 0.1, 0.5))
        if p_title > 0:
            tf  = F(62, bold=True)
            lay = text_layer(textwrap.shorten(self.title, 54, placeholder='â€¦'), tf, C_TEXT, p_title)
            frame = composite_rgba(frame, lay, (72, 22))
            draw  = ImageDraw.Draw(frame)
            uw = int(lay.width * ease_out(progress(t, 0.4, 0.35)))
            if uw > 0:
                draw.rectangle([(72, 98), (72 + uw, 102)],
                                fill=(*C_GREEN, alpha_int(p_title)))

        # Bullets in two columns as glassmorphism cards
        bf = F(34)
        for i, point in enumerate(self.points):
            p_b = ease_out(progress(t, 0.7 + i * 0.55, 0.4))
            if p_b <= 0:
                continue

            col    = i % 2
            row    = i // 2
            bx     = 60  + col * (W // 2 + 20)
            by     = 145 + row * 140
            bw_c   = W // 2 - 80
            bh_c   = 118
            icon_c = self._BULLET_COLS[i % len(self._BULLET_COLS)]
            x_off  = int(60 * (1 - p_b)) * (-1 if col == 0 else 1)

            card = rounded_rect_rgba(bw_c, bh_c,
                                      (*C_BG2, alpha_int(p_b * 0.88)),
                                      radius=16,
                                      border=(*icon_c, alpha_int(p_b * 0.5)))
            frame = composite_rgba(frame, card, (bx + x_off, by))
            draw  = ImageDraw.Draw(frame)

            # Icon badge
            draw.ellipse([(bx + x_off + 16, by + 16),
                           (bx + x_off + 52, by + 52)],
                          fill=(*icon_c, alpha_int(p_b * 0.25)))
            draw.text((bx + x_off + 22, by + 19),
                      self._BULLET_ICONS[i % len(self._BULLET_ICONS)],
                      font=F(24, bold=True), fill=(*icon_c, alpha_int(p_b)))

            for li, wl in enumerate(textwrap.wrap(point[:70], 30)[:2]):
                lay = text_layer(wl, bf, C_TEXT, p_b)
                frame = composite_rgba(frame, lay, (bx + x_off + 68, by + 18 + li * 42))

        draw_visualizer(frame, t)
        return np.array(frame)


class BrandedIntroRenderer:
    """YouTube-style branded intro: 6 s animated title card with particles."""
    DUR = 3.0

    def __init__(self, data: dict):
        self.title          = data.get("title", "Code Narrator")
        self.repo_url       = data.get("repo_url", "")
        self.chapter_count  = data.get("chapter_count", 0)
        self._particles     = self._init_particles()

    def _init_particles(self):
        rng = random.Random(99)
        return [
            {
                "x":     rng.uniform(0, W),
                "y":     rng.uniform(0, H),
                "vx":    rng.uniform(-25, 25),
                "vy":    rng.uniform(-60, -10),
                "size":  rng.uniform(2, 5),
                "phase": rng.uniform(0, 6.28),
            }
            for _ in range(90)
        ]

    def make_frame(self, t: float) -> np.ndarray:
        frame = grad_bg(((5, 5, 15), (18, 10, 40)))
        draw  = ImageDraw.Draw(frame)

        # Animated particles
        particle_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(particle_layer)
        for p in self._particles:
            px   = (p["x"] + p["vx"] * t) % W
            py   = (p["y"] + p["vy"] * t) % H
            alph = int(clamp01((0.5 + 0.5 * math.sin(t * 2 + p["phase"]))) * 160)
            s    = p["size"]
            pd.ellipse([(px - s, py - s), (px + s, py + s)],
                       fill=(*C_ACCENT, alph))
        frame = composite_rgba(frame, particle_layer)

        # Pulsing glow circle
        pulse = 0.5 + 0.5 * math.sin(t * 2.2)
        glow  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd    = ImageDraw.Draw(glow)
        for r in [350, 260, 180]:
            a = int(18 * pulse * (180 / r))
            gd.ellipse([(W//2 - r, H//2 - r), (W//2 + r, H//2 + r)],
                       fill=(*C_ACCENT2, a))
        frame = composite_rgba(frame, glow)

        # Title fade-in 0.3 â†’ 1.3 s
        p_title = ease_out(progress(t, 0.3, 1.0))
        if p_title > 0:
            tf   = F(100, bold=True)
            text = self.title[:28]
            lay  = text_layer(text, tf, C_TEXT, p_title)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, H // 2 - 100))

        # Accent underline sweeps in at 0.9 s
        p_line = ease_out(progress(t, 0.9, 0.5))
        if p_line > 0:
            draw = ImageDraw.Draw(frame)
            lw   = int(500 * p_line)
            draw.rectangle([(W//2 - lw//2, H//2 + 14), (W//2 + lw//2, H//2 + 18)],
                           fill=(*C_ACCENT, int(220 * p_line)))

        # Chapter count subtitle
        p_sub = ease_out(progress(t, 1.0, 0.7))
        if p_sub > 0:
            txt = (f"{self.chapter_count} Chapters Â· AI-Generated Tutorial"
                   if self.chapter_count else "AI-Generated Tutorial")
            lay = text_layer(txt, F(36), C_ACCENT, p_sub)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, H // 2 + 40))

        # Repo URL
        p_url = ease_in_out(progress(t, 1.5, 0.8))
        if p_url > 0 and self.repo_url:
            lay = text_layer(self.repo_url[:70], F(26, mono=True), C_MUTED, p_url * 0.8)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, H // 2 + 100))

        # Bottom branding bar sweeps in at 2 s
        p_bar = ease_out(progress(t, 2.0, 0.6))
        if p_bar > 0:
            draw = ImageDraw.Draw(frame)
            bw   = int(420 * p_bar)
            draw.rectangle([(W//2 - bw//2, H - 56), (W//2 + bw//2, H - 52)],
                           fill=(*C_ACCENT, int(180 * p_bar)))
            lf  = F(22, bold=True)
            wtxt = "Code Narrator"
            draw.text(((W - txt_w(draw, wtxt, lf)) // 2, H - 44), wtxt,
                      font=lf, fill=(*C_ACCENT, int(160 * p_bar)))

        draw_visualizer(frame, t)
        return np.array(frame)


class ChapterTransitionRenderer:
    """3 s chapter card with sweep, big number, title and progress bar."""
    DUR = 2.0

    def __init__(self, data: dict):
        self.chapter_num    = int(data.get("chapter_number", 1))
        self.chapter_title  = data.get("chapter_title", "")
        self.total_chapters = max(int(data.get("total_chapters", 1)), 1)

    def make_frame(self, t: float) -> np.ndarray:
        frame = grad_bg(((8, 8, 20), (22, 16, 50)))
        draw  = ImageDraw.Draw(frame)

        # Horizontal accent sweep
        p_sweep = ease_out(progress(t, 0.0, 0.45))
        sweep_x = int(W * p_sweep)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od      = ImageDraw.Draw(overlay)
        od.rectangle([(0, 0), (sweep_x, H)], fill=(*C_ACCENT2, 28))
        frame = composite_rgba(frame, overlay)

        # Thin accent line
        draw = ImageDraw.Draw(frame)
        line_w = int(W * ease_out(progress(t, 0.1, 0.45)))
        if line_w > 0:
            draw.rectangle([(0, H//2 - 2), (line_w, H//2 + 2)], fill=C_ACCENT)

        # Big ghost chapter number
        p_num = ease_out(progress(t, 0.15, 0.4))
        if p_num > 0:
            nf  = F(160, bold=True)
            lay = text_layer(f"{self.chapter_num:02d}", nf, C_ACCENT, p_num * 0.12)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, H // 2 - 150))

        # "CHAPTER X" label
        p_label = ease_out(progress(t, 0.3, 0.4))
        if p_label > 0:
            lay = text_layer(f"CHAPTER {self.chapter_num}",
                             F(30, bold=True), C_ACCENT, p_label)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, H // 2 - 52))

        # Chapter title
        p_title = ease_out(progress(t, 0.5, 0.5))
        if p_title > 0:
            lay = text_layer(self.chapter_title[:44], F(56, bold=True), C_TEXT, p_title)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, H // 2 + 10))

        # Progress bar at bottom
        p_prog = ease_out(progress(t, 0.6, 0.4))
        if p_prog > 0:
            draw   = ImageDraw.Draw(frame)
            bar_y  = H - 90
            bar_x  = 100
            bar_w  = W - 200
            draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + 10)],
                                   radius=5, fill=C_BG3)
            frac   = self.chapter_num / self.total_chapters
            fw     = int(bar_w * frac * p_prog)
            if fw > 0:
                draw.rounded_rectangle([(bar_x, bar_y), (bar_x + fw, bar_y + 10)],
                                       radius=5, fill=C_ACCENT)
            # Chapter position dots
            step = bar_w / self.total_chapters
            for ci in range(self.total_chapters):
                dot_x = int(bar_x + (ci + 0.5) * step)
                color = C_ACCENT if ci < self.chapter_num else C_BG3
                r     = 7 if ci + 1 == self.chapter_num else 4
                draw.ellipse([(dot_x - r, bar_y + 5 - r), (dot_x + r, bar_y + 5 + r)],
                             fill=color)

        return np.array(frame)


class OutroRenderer:
    """10 s YouTube-style outro: chapter recap, GitHub CTA, star badge."""
    DUR = 4.5

    def __init__(self, data: dict):
        self.title    = data.get("title", "Code Narrator")
        self.chapters = data.get("chapters", [])[:8]
        self.repo_url = data.get("repo_url", "")
        self._base    = self._prebuild()

    def _prebuild(self) -> Image.Image:
        img  = grad_bg(((5, 5, 15), (22, 12, 45)))
        img  = spotlight(img, W // 2, H // 2, 700, color=(50, 80, 180), intensity=22)
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0, 0), (W, 5)], fill=C_ACCENT)
        draw.rectangle([(0, H - 5), (W, H)], fill=C_ACCENT)
        draw_watermark(img)
        return img

    def make_frame(self, t: float) -> np.ndarray:
        frame = self._base.copy()

        # "Tutorial Complete!" heading
        p_h = ease_out(progress(t, 0.0, 0.8))
        if p_h > 0:
            lay = text_layer("Tutorial Complete!", F(74, bold=True), C_TEXT, p_h)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, 55))

        # Tutorial title in accent
        p_sub = ease_out(progress(t, 0.4, 0.6))
        if p_sub > 0:
            lay = text_layer(self.title[:50], F(38, italic=True), C_ACCENT, p_sub)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, 160))

        # Chapter list with animated checkmarks (two columns, non-overlapping)
        cf = F(28)
        for i, ch in enumerate(self.chapters):
            p_ch = ease_out(progress(t, 0.9 + i * 0.25, 0.3))
            if p_ch > 0:
                col   = i % 2
                row   = i // 2
                # col0 at x=110, col1 at x=1010 â€” 900 px apart, no overlap
                cx    = 110 + col * 900
                cy    = 255 + row * 72

                ck    = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ckd   = ImageDraw.Draw(ck)
                ckd.ellipse([(cx, cy + 4), (cx + 26, cy + 30)],
                            fill=(*C_GREEN, alpha_int(p_ch)))
                ckd.text((cx + 4, cy + 4), "âœ“", font=F(18, bold=True),
                         fill=(*C_BG, alpha_int(p_ch)))
                frame = composite_rgba(frame, ck)
                label = textwrap.shorten(ch, 32, placeholder="â€¦")
                lay   = text_layer(label, cf, C_TEXT, p_ch)
                frame = composite_rgba(frame, lay, (cx + 34, cy))

        # GitHub link box
        p_gh = ease_out(progress(t, 4.5, 0.8))
        if p_gh > 0 and self.repo_url:
            box_y  = H - 210
            gh_box = rounded_rect_rgba(740, 68, (*C_BG3, alpha_int(p_gh * 0.85)),
                                        radius=14, border=(*C_BORDER, alpha_int(p_gh)))
            frame = composite_rgba(frame, gh_box, ((W - 740) // 2, box_y))
            draw  = ImageDraw.Draw(frame)
            uf    = F(26, mono=True)
            tw    = txt_w(draw, self.repo_url[:60], uf)
            draw.text(((W - tw) // 2, box_y + 20),
                      self.repo_url[:60], font=uf,
                      fill=(*C_ACCENT, alpha_int(p_gh)))

        # "Star on GitHub" CTA
        p_cta = ease_out(progress(t, 5.5, 1.0))
        if p_cta > 0:
            lay = text_layer("â­  Star this repo on GitHub!", F(44, bold=True), C_YELLOW, p_cta)
            frame = composite_rgba(frame, lay, ((W - lay.width) // 2, H - 115))

        draw_visualizer(frame, t)
        return np.array(frame)


def render_clip_sync(renderer_cls, data: dict, out_path: str) -> None:
    """Render an animated clip to *out_path* (no audio).  Used by AssembleVideo."""
    import numpy as _np
    from moviepy import VideoClip  # type: ignore

    renderer = renderer_cls(data)
    dur      = renderer_cls.DUR
    clip     = VideoClip(renderer.make_frame, duration=dur)
    clip.write_videofile(out_path, fps=FPS, codec="libx264",
                         preset="ultrafast", audio=False, logger=None,
                         ffmpeg_params=["-vf", f"scale={_OUT_W}:{_OUT_H}",
                                        "-sws_flags", "fast_bilinear"])


# â”€â”€ Main node â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _parse_content(raw) -> dict:
    """Normalise display_content to dict regardless of LLM format."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        lines = raw.strip().splitlines()
        # Try to detect TERM/DEFINITION pattern
        d = {}
        for line in lines:
            for prefix in ["TERM:", "DEFINITION:", "CONCEPT:"]:
                if line.upper().startswith(prefix):
                    key = prefix.rstrip(":").lower()
                    d[key] = line.split(":", 1)[1].strip()
        if not d:
            d = {"text": raw, "title": lines[0] if lines else ""}
        return d
    return {}


async def _fetch_diagram(mermaid_src: str) -> Optional[Image.Image]:
    clean = mermaid_src.replace("\r\n", "\n").strip()
    clean = re.sub(r'[^\x09\x0A\x20-\x7E]', ' ', clean)
    encoded = base64.urlsafe_b64encode(clean.encode()).decode()
    url = f"https://mermaid.ink/img/{encoded}?bgColor=0d1117"
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and len(resp.content) > 800:
                return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as exc:
        logger.warning("mermaid.ink: %s", exc)
    return None


def _make_moviepy_clip(renderer, duration: float):
    from moviepy import VideoClip
    return VideoClip(renderer.make_frame, duration=duration)


class GenerateVisuals(AsyncNode):

    async def prep(self, shared: dict) -> dict:
        return {
            "video_script": shared["video_script"],
            "output_dir":   shared["output_dir"],
        }

    async def exec(self, prep_result: dict) -> List[str]:
        segments = prep_result["video_script"]
        out_dir  = Path(prep_result["output_dir"]) / "visuals"
        out_dir.mkdir(parents=True, exist_ok=True)

        total = len(segments)
        print(f"GenerateVisuals: {total} segments â€” rendering in parallel")

        # â”€â”€ Parallel rendering with CPU semaphore â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Clips are fully independent â€” no reason to render them one-by-one.
        # On cloud/low-CPU machines (e.g. Render free tier with 0.1 shared CPU),
        # too many concurrent renders cause thrashing. Cap workers conservatively.
        import multiprocessing, os as _os
        cpu_count   = multiprocessing.cpu_count()
        # On Render/cloud free tier, cpu_count is host CPUs but we only get a slice.
        # Check for explicit env override, else use conservative default for cloud.
        _cloud = bool(_os.environ.get("RENDER") or _os.environ.get("RAILWAY_ENVIRONMENT"))
        max_workers = int(_os.environ.get("RENDER_MAX_WORKERS", 2 if _cloud else min(cpu_count, 4)))
        sem         = asyncio.Semaphore(max_workers)
        done        = [0]

        async def _render_one(i: int, seg: dict) -> str:
            seg_type = seg.get("type", "slide")
            raw      = seg.get("display_content", {})
            data     = _parse_content(raw)
            out_path = out_dir / f"segment_{i:03d}.mp4"

            async with sem:
                try:
                    renderer, dur = await self._make_renderer(seg_type, data)
                    clip = await asyncio.to_thread(_make_moviepy_clip, renderer, dur)
                    await asyncio.to_thread(
                        clip.write_videofile,
                        str(out_path), fps=FPS,
                        codec="libx264", preset="ultrafast",
                        audio=False, logger=None,
                        ffmpeg_params=["-vf", f"scale={_OUT_W}:{_OUT_H}",
                                       "-sws_flags", "fast_bilinear"],
                    )
                except Exception as exc:
                    logger.warning("Segment %d failed (%s): %s â€” black frame", i, seg_type, exc)
                    await asyncio.to_thread(self._write_black_clip, str(out_path))

            done[0] += 1
            if done[0] % 4 == 0 or done[0] == total:
                print(f"GenerateVisuals: {done[0]}/{total} clips done")
            return str(out_path)

        results = await asyncio.gather(
            *[_render_one(i, seg) for i, seg in enumerate(segments)]
        )

        # Preserve original ordering (gather returns results in submission order)
        paths = list(results)
        print(f"GenerateVisuals: all {total} clips rendered âœ“")
        return paths

    async def _make_renderer(self, seg_type: str, data: dict):
        """Return (renderer, duration) for given segment type."""
        if seg_type == "title":
            return TitleRenderer(data), TitleRenderer.DUR
        elif seg_type == "chapter_intro":
            return ChapterIntroRenderer(data), ChapterIntroRenderer.DUR
        elif seg_type == "definition":
            return DefinitionRenderer(data), DefinitionRenderer.DUR
        elif seg_type == "code":
            return CodeRenderer(data), CodeRenderer.DUR
        elif seg_type in ("architecture", "diagram"):
            diag = await _fetch_diagram(
                data.get("mermaid_source", data.get("text", ""))
            )
            return ArchitectureRenderer(data, diag), ArchitectureRenderer.DUR
        elif seg_type == "summary":
            return SummaryRenderer(data), SummaryRenderer.DUR
        elif seg_type == "bullets":
            return BulletsRenderer(data), BulletsRenderer.DUR
        else:
            return SlideRenderer(data), SlideRenderer.DUR

    def _write_black_clip(self, path: str) -> None:
        from moviepy import VideoClip
        import numpy as np
        W_, H_ = 1920, 1080
        black = VideoClip(lambda t: np.zeros((H_, W_, 3), dtype=np.uint8), duration=4.5)
        black.write_videofile(path, fps=FPS, codec="libx264",
                              preset="ultrafast", audio=False, logger=None,
                              ffmpeg_params=["-vf", f"scale={_OUT_W}:{_OUT_H}",
                                             "-sws_flags", "fast_bilinear"])

    async def post(self, shared: dict, prep_result, exec_result) -> str:
        shared["visual_paths"] = exec_result
        return "default"

