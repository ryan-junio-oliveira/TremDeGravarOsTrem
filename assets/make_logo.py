"""Gera a marca GravaTrem: assets/logo.svg, PNGs e icon.ico.

Marca: tile escuro arredondado + monitor com ponto REC vermelho.
Rode:  python assets/make_logo.py   (na raiz do projeto)
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
S = 512

# Paleta (docs/MARCA.md)
BG_TOP, BG_BOT = (38, 45, 64), (20, 24, 33)
RED = (229, 72, 77)
WHITE = (232, 234, 240)
MUTED = (154, 163, 181)


def tile(size=S):
    top = np.array(BG_TOP, dtype=np.float32)
    bot = np.array(BG_BOT, dtype=np.float32)
    t = np.linspace(0, 1, size, dtype=np.float32)[:, None, None]
    grad = (top * (1 - t) + bot * t).astype(np.uint8)
    img = Image.fromarray(np.repeat(grad, size, axis=1), "RGB").convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=int(size * 0.22), fill=255)
    img.putalpha(mask)
    return img


def mark(size=S):
    k = size / S
    img = tile(size)
    d = ImageDraw.Draw(img, "RGBA")
    # glow + ponto REC
    cx, cy = int(256 * k), int(240 * k)
    d.ellipse([cx - 80 * k, cy - 80 * k, cx + 80 * k, cy + 80 * k],
              fill=RED + (70,))
    d.ellipse([cx - 52 * k, cy - 52 * k, cx + 52 * k, cy + 52 * k], fill=RED)
    # tela (monitor)
    d.rounded_rectangle([96 * k, 140 * k, 416 * k, 340 * k], radius=36 * k,
                        outline=WHITE, width=max(1, int(26 * k)))
    # pe: haste + base
    d.line([256 * k, 340 * k, 256 * k, 372 * k], fill=MUTED, width=max(1, int(22 * k)))
    d.line([198 * k, 390 * k, 314 * k, 390 * k], fill=MUTED, width=max(1, int(22 * k)))
    return img


WORDMARK = """<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="300" viewBox="0 0 1024 300">
  <rect width="1024" height="300" rx="48" fill="#1a1e29"/>
  <circle cx="150" cy="128" r="58" fill="#e5484d"/>
  <rect x="236" y="78" width="260" height="100" rx="26" fill="none" stroke="#e8eaf0" stroke-width="22"/>
  <line x1="366" y1="178" x2="366" y2="206" stroke="#9aa3b5" stroke-width="18"/>
  <line x1="322" y1="218" x2="410" y2="218" stroke="#9aa3b5" stroke-width="18"/>
  <text x="540" y="170" font-family="Segoe UI, Arial, sans-serif" font-size="96" font-weight="800" fill="#e8eaf0">Grava<tspan fill="#e5484d">Trem</tspan></text>
  <text x="544" y="228" font-family="Segoe UI, Arial, sans-serif" font-size="34" font-weight="600" letter-spacing="6" fill="#9aa3b5">TREM DE GRAVAR OS TREM</text>
</svg>
"""


def main():
    HERE.mkdir(parents=True, exist_ok=True)
    big = mark()
    big.save(HERE / "logo-512.png")
    for n in (256, 128, 64, 32):
        big.resize((n, n), Image.LANCZOS).save(HERE / f"logo-{n}.png")
    (HERE / "logo.svg").write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#262d40"/><stop offset="1" stop-color="#141821"/>
  </linearGradient></defs>
  <rect width="512" height="512" rx="112" fill="url(#g)"/>
  <circle cx="256" cy="240" r="80" fill="#e5484d" opacity="0.28"/>
  <circle cx="256" cy="240" r="52" fill="#e5484d"/>
  <rect x="96" y="140" width="320" height="200" rx="36" fill="none" stroke="#e8eaf0" stroke-width="26"/>
  <line x1="256" y1="340" x2="256" y2="372" stroke="#9aa3b5" stroke-width="22"/>
  <line x1="198" y1="390" x2="314" y2="390" stroke="#9aa3b5" stroke-width="22"/>
</svg>
""", encoding="utf-8")
    (HERE / "wordmark.svg").write_text(WORDMARK, encoding="utf-8")
    # ICO multi-resolucao para app + instalador
    big.save(Path(__file__).resolve().parent.parent / "icon.ico",
             sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("marca gerada:", sorted(p.name for p in HERE.iterdir()))


if __name__ == "__main__":
    main()
