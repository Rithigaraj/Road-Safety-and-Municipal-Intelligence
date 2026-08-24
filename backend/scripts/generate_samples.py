"""Generate synthetic sample images for each of the seven problem classes.

Images are designed to contain clear, strong visual signals that the
self-contained heuristic detector can find, so the whole pipeline can be
demonstrated without downloading any model weights.
"""
import os
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"
W = H = 512


def _canvas(base=(105, 108, 112)) -> Image.Image:
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[...] = base
    noise = np.random.default_rng().normal(0, 6, (H, W, 3))
    img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(img)


def _texture(img: Image.Image, rng: random.Random, scale: float = 0.5):
    """Add speckled asphalt texture."""
    arr = np.asarray(img).astype(np.float32)
    speck = np.random.default_rng().integers(0, 4, (H, W, 1)).astype(np.float32) * scale
    arr = np.clip(arr + speck, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _pothole():
    img = _canvas((112, 116, 120))
    d = ImageDraw.Draw(img)
    d.ellipse([150, 150, 380, 330], fill=(35, 38, 42))       # the hole
    d.ellipse([160, 158, 372, 322], fill=(60, 64, 68))       # cracked rim
    inner = np.zeros((H, W, 3), dtype=np.uint8)
    inner[...] = (24, 26, 30)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse([190, 180, 340, 300], fill=255)
    img = Image.composite(Image.fromarray(inner), img, mask)
    return _texture(img, random.Random(1))


def _road_crack():
    img = _canvas((115, 118, 122))
    d = ImageDraw.Draw(img)
    # a winding thin crack branching into two
    d.line([(60, 60), (200, 190), (330, 260), (470, 330)], fill=(16, 18, 20), width=2)
    d.line([(200, 190), (260, 330), (320, 460)], fill=(18, 20, 22), width=2)
    d.line([(330, 260), (430, 420)], fill=(20, 22, 24), width=2)
    return _texture(img, random.Random(2))


def _garbage():
    img = _canvas((120, 123, 126))
    d = ImageDraw.Draw(img)
    rng = random.Random(3)
    colors = [(210, 40, 40), (30, 120, 210), (40, 170, 60), (230, 200, 30),
              (220, 110, 30), (120, 60, 160), (240, 240, 240), (20, 20, 20)]
    for _ in range(28):
        x, y = rng.randint(130, 380), rng.randint(150, 330)
        r = rng.randint(6, 18)
        d.ellipse([x - r, y - r, x + r, y + r], fill=rng.choice(colors))
    # a couple of black bags (kept low-saturation so they don't confuse the detector)
    d.ellipse([210, 260, 300, 320], fill=(45, 45, 45))
    d.ellipse([300, 280, 380, 340], fill=(35, 35, 38))
    return _texture(img, rng)


def _water_leakage():
    img = _canvas((140, 143, 146))
    d = ImageDraw.Draw(img)
    # dark glossy blue puddle spreading from a pipe leak
    d.ellipse([170, 210, 400, 330], fill=(12, 44, 150))
    d.ellipse([190, 220, 390, 318], fill=(18, 58, 175))
    d.ellipse([220, 235, 360, 305], fill=(30, 80, 200))       # glossy highlight
    # a leaking pipe/crack at the top of the puddle
    d.rectangle([240, 150, 252, 216], fill=(30, 32, 36))
    d.ellipse([232, 140, 260, 160], fill=(25, 27, 31))
    return _texture(img, random.Random(4))


def _broken_streetlight():
    img = np.zeros((H, W, 3), dtype=np.uint8)
    # night scene: dark sky, slightly lighter ground
    img[0:int(H * 0.55), :] = (70, 74, 82)
    img[int(H * 0.55):, :] = (92, 95, 100)
    noise = np.random.default_rng().normal(0, 2, (H, W, 3))
    base = Image.fromarray(np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(base)
    # pole (dark, vertical) anchored near the ground
    d.rectangle([240, int(H * 0.5), 268, H - 1], fill=(14, 15, 18))
    # lamp arm
    d.rectangle([240, int(H * 0.44), 330, int(H * 0.46)], fill=(14, 15, 18))
    # broken lamp housing: dark, no glow
    d.ellipse([320, int(H * 0.40), 360, int(H * 0.46)], fill=(30, 32, 36))
    return base


def _damaged_traffic_sign():
    img = _canvas((118, 121, 124))
    d = ImageDraw.Draw(img)
    # road-sign pole
    d.rectangle([150, 150, 158, H - 1], fill=(70, 72, 76))
    # green direction sign (low blue-dominance so it reads as a real sign under our heuristics)
    d.rectangle([180, 140, 420, 260], fill=(70, 150, 85), outline=(45, 100, 55), width=4)
    # big dark damage: missing chunk
    d.polygon([(330, 140), (420, 140), (420, 200), (360, 200), (330, 240)], fill=(22, 24, 28))
    # radial crack lines from the damage
    d.line([(330, 200), (280, 260)], fill=(30, 32, 36), width=3)
    d.line([(350, 240), (340, 260)], fill=(30, 32, 36), width=3)
    # small intact white symbol on the surviving part
    d.rectangle([200, 160, 230, 220], fill=(235, 238, 240))
    return _texture(img, random.Random(5))


def _blocked_drainage():
    img = _canvas((120, 123, 126))
    # grille band at the bottom with visible gaps between bars
    d = ImageDraw.Draw(img)
    y = int(H * 0.78)
    for x in range(0, W, 12):
        d.rectangle([x, y, x + 7, H - 1], fill=(70, 72, 76))
    # debris pile sitting on top of the grille (dense dark mass)
    d.polygon([(140, y), (200, int(H * 0.66)), (300, int(H * 0.64)),
               (360, int(H * 0.68)), (380, y)], fill=(45, 40, 34))
    d.ellipse([170, int(H * 0.66), 240, y], fill=(52, 48, 42))
    d.ellipse([250, int(H * 0.64), 330, y], fill=(56, 50, 44))
    d.ellipse([330, int(H * 0.68), 390, y], fill=(48, 46, 42))
    # murky standing water in front of the blocked drain (grey, low blue dominance)
    d.rectangle([0, y, 140, H - 1], fill=(50, 55, 70))
    return _texture(img, random.Random(6))


GENERATORS = {
    "pothole": _pothole,
    "road_crack": _road_crack,
    "garbage": _garbage,
    "water_leakage": _water_leakage,
    "broken_streetlight": _broken_streetlight,
    "damaged_traffic_sign": _damaged_traffic_sign,
    "blocked_drainage": _blocked_drainage,
}


def main():
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    for name, gen in GENERATORS.items():
        out = SAMPLES_DIR / f"{name}.jpg"
        gen().convert("RGB").save(out, quality=90)
        print(f"generated {out}")


if __name__ == "__main__":
    sys.exit(main())
